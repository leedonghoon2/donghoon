import asyncio
import ccxt
from datetime import datetime, timedelta
from tqdm import tqdm
import aiohttp

async def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {"chat_id": chat_id, "text": message}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"Telegram message failed: {response.status}")

async def log_and_notify(message, telegram_token, chat_id):
    print(message)
    await send_telegram_message(telegram_token, chat_id, message)

def fetch_binance_candles(exchange, symbol, timeframe='1h', limit=12):
    """
    바이낸스 선물 시장에서 캔들 데이터를 가져옵니다.
    - timeframe: 예: '1h'는 1시간봉
    - limit: 가져올 캔들의 개수
    """
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return candles
    except Exception as e:
        print(f"Error fetching candles for {symbol}: {e}")
        return []

def analyze_candles(candles, num_candles):
    """
    캔들 데이터를 분석하여 거래 조건이 충족되는지 확인합니다.
    - 조건: 타겟 캔들의 거래량 >= 이전 n개 캔들의 평균 거래량 * 7.
    - 타겟 캔들에서 양의 가격 변동.
    """
    if len(candles) < num_candles + 2:
        return None, None, None, None, []

    target_candle = candles[-2]  # H-1 캔들 (직전 한 시간)
    previous_candles = candles[-(num_candles + 2):-2]  # 타겟 캔들 이전의 n개 캔들

    # 거래량 계산
    previous_volumes = [candle[5] for candle in previous_candles]
    average_volume = sum(previous_volumes) / len(previous_volumes)
    volume_threshold = 7 * average_volume
    target_volume = target_candle[5]

    # 가격 변동 계산
    opening_price = target_candle[1]
    closing_price = target_candle[4]
    target_change = (closing_price - opening_price) / opening_price * 100

    return target_volume, average_volume, volume_threshold, target_change, previous_volumes

async def process_symbol(symbol, exchange, num_candles):
    candles = fetch_binance_candles(exchange, symbol, timeframe='1h', limit=num_candles + 2)
    if not candles:
        return None, None

    target_volume, average_volume, volume_threshold, target_change, previous_volumes = analyze_candles(candles, num_candles=num_candles)
    message = (
        f"{symbol} 기준봉 정보:\n"
        f"- 시간: {datetime.fromtimestamp(candles[-2][0] / 1000).isoformat()}\n"
        f"- 거래량: {target_volume}\n"
        f"- 변동률: {target_change:.2f}%\n"
        f"- 이전 {num_candles}개봉 거래량 리스트: {previous_volumes}\n"
        f"- 이전 {num_candles}개봉 평균 거래량: {average_volume}\n"
        f"- 평균 거래량의 7배값: {volume_threshold}\n"
    )
    return message, target_volume >= volume_threshold and target_change > 0

def open_short_position(exchange, symbol, margin_usd, open_positions):
    """
    바이낸스 선물 시장에서 숏 포지션을 엽니다.
    """
    try:
        exchange.load_markets()
        price = exchange.fetch_ticker(symbol)['last']
        amount = margin_usd / price
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='sell',
            amount=amount
        )
        open_positions.append({
            'symbol': symbol,
            'opened_at': datetime.now(),
            'order': order,
            'margin': margin_usd,
            'amount': amount,
            'alert_count': 0
        })
        return order
    except Exception as e:
        print(f"Error opening position for {symbol}: {e}")
        return None

def close_position(exchange, position):
    """
    바이낸스 선물 시장에서 열린 포지션을 청산합니다.
    """
    try:
        symbol = position['symbol']
        amount = position['amount']
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=amount
        )
        return order
    except Exception as e:
        print(f"Error closing position for {symbol}: {e}")
        return None

async def manage_open_positions(open_positions, exchange, telegram_token, chat_id):
    """
    열린 포지션을 관리하며, 각 포지션에 대해 알림을 발송합니다.
    """
    for position in open_positions[:]:
        position['alert_count'] += 1
        await log_and_notify(
            f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.",
            telegram_token,
            chat_id
        )
        if position['alert_count'] >= 4:  # 예: 알림 4회 후 청산
            try:
                close_position(exchange, position)
                open_positions.remove(position)
                await log_and_notify(
                    f"Position closed for {position['symbol']}",
                    telegram_token,
                    chat_id
                )
            except Exception as e:
                await log_and_notify(
                    f"Error closing position for {position['symbol']}: {e}",
                    telegram_token,
                    chat_id
                )

async def recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles):
    """
    시간 불일치 심볼을 재검증합니다.
    """
    valid_symbols = []
    for symbol in mismatched_symbols[:]:
        candles = fetch_binance_candles(exchange, symbol, timeframe='1h', limit=num_candles + 2)
        if candles:
            target_volume, average_volume, volume_threshold, target_change, _ = analyze_candles(candles, num_candles=num_candles)
            if target_volume >= volume_threshold and target_change > 0:
                valid_symbols.append(symbol)
    return valid_symbols

async def main():
    telegram_token = ""  # Telegram 봇 토큰을 입력하세요.
    chat_id = ""  # Telegram Chat ID를 입력하세요.

    api_key = ""  # 바이낸스 API 키를 입력하세요.
    api_secret = ""  # 바이낸스 API 비밀 키를 입력하세요.

    entry_amount_usd = 100  # 각 거래의 진입 금액 (USD 기준)

    num_candles = 10  # 이전 n개봉을 분석할 수

    # 바이낸스 선물 클라이언트 초기화
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},  # 선물 시장 사용 설정
    })

    exchange.load_markets()
    binance_symbols = []
    for symbol in exchange.symbols:
        try:
            market = exchange.market(symbol)
            if symbol.endswith('USDT') and market['info']['contractType'] == 'PERPETUAL':
                standardized_symbol = symbol.split(':')[0]  # 'ZRO/USDT:USDT' -> 'ZRO/USDT'
                binance_symbols.append(standardized_symbol)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")

    binance_symbols = list(set(binance_symbols))  # 중복 제거

    open_positions = []
    mismatched_symbols = []

    while True:
        start_time = datetime.now()
        next_run_time = (start_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        # 병렬 처리로 심볼 데이터 가져오기
        tasks = [process_symbol(symbol, exchange, num_candles=num_candles) for symbol in binance_symbols]
        results = await asyncio.gather(*tasks)

        trading_list = []

        for message, is_trading_candidate in results:
            if is_trading_candidate:
                trading_list.append(message.split(' ')[0])
            elif not is_trading_candidate and message:
                mismatched_symbols.append(message.split(' ')[0])

        # 시간 불일치 심볼 재검증
        resolved_symbols = await recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles)
        trading_list.extend(resolved_symbols)

        # 중복 제거
        trading_list = list(set(trading_list))

        # 매매 대상 심볼 출력
        await log_and_notify(f"Trading candidates: {trading_list}", telegram_token, chat_id)

        for symbol in trading_list:
            order = open_short_position(exchange, symbol, entry_amount_usd, open_positions)
            if order:
                await log_and_notify(f"Short position opened for {symbol}:{order}", telegram_token, chat_id)

        # 열린 포지션 관리
        await manage_open_positions(open_positions, exchange, telegram_token, chat_id)

        now = datetime.now()
        wait_time = (next_run_time - now).total_seconds()
        if wait_time > 0:
            await log_and_notify(f"Waiting {wait_time:.2f} seconds for the next cycle.", telegram_token, chat_id)
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    asyncio.run(main())
