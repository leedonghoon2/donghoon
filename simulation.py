import asyncio
import ccxt
from datetime import datetime, timedelta
from tqdm import tqdm
import aiohttp

# 텔레그램 메시지 발송 함수
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

# 바이낸스에서 캔들 데이터를 가져오는 함수
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

# 캔들 데이터를 분석하는 함수
def analyze_candles(candles, num_candles):
    """
    캔들 데이터를 분석하여 거래 조건이 충족되는지 확인합니다.
    - 조건: 타겟 캔들의 거래량 >= 이전 n개 캔들의 평균 거래량 * 3.
    - 타겟 캔들에서 양의 가격 변동.
    """
    if len(candles) < num_candles + 2:
        return None, None, None, None, []

    target_candle = candles[-2]  # H-1 캔들 (직전 한 시간)
    previous_candles = candles[-(num_candles + 2):-2]  # 타겟 캔들 이전의 n개 캔들

    # 거래량 계산
    previous_volumes = [candle[5] for candle in previous_candles]
    average_volume = sum(previous_volumes) / len(previous_volumes)
    volume_threshold = 3 * average_volume  # 여기서는 3배로 설정 (원하는 배수로 조정 가능)
    target_volume = target_candle[5]

    # 가격 변동 계산
    opening_price = target_candle[1]
    closing_price = target_candle[4]
    target_change = (closing_price - opening_price) / opening_price * 100

    return target_volume, average_volume, volume_threshold, target_change, previous_volumes

# 심볼 당 캔들 데이터 처리 함수
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
        f"- 평균 거래량의 3배값: {volume_threshold}\n"
    )
    return message, target_volume >= volume_threshold and target_change > 0

# ------------------------------
# 매매 시뮬레이션 관련 함수들
# ------------------------------

def open_short_position_simulation(exchange, symbol, margin_usd, open_positions):
    """
    바이낸스 선물 시장에서 숏 포지션을 여는 시뮬레이션 함수입니다.
    실제 주문을 보내지 않고, 현재 가격 기준으로 포지션 정보를 기록합니다.
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = margin_usd / price
        simulated_order = {
            'symbol': symbol,
            'price': price,
            'amount': amount,
            'side': 'sell',
            'timestamp': datetime.now()
        }
        open_positions.append({
            'symbol': symbol,
            'opened_at': datetime.now(),
            'open_price': price,    # 포지션 개시 가격 저장
            'margin': margin_usd,
            'amount': amount,
            'alert_count': 0,
            'order': simulated_order
        })
        return simulated_order
    except Exception as e:
        print(f"Error simulating opening position for {symbol}: {e}")
        return None

def close_position_simulation(exchange, position):
    """
    바이낸스 선물 시장에서 열린 포지션을 청산하는 시뮬레이션 함수입니다.
    현재 가격과 포지션 개시 가격을 비교하여 수익을 계산합니다.
    """
    try:
        symbol = position['symbol']
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        open_price = position['open_price']
        # 숏 포지션의 경우, (개시가 - 청산가) * amount가 수익입니다.
        profit = (open_price - current_price) * position['amount']
        simulated_order = {
            'symbol': symbol,
            'price': current_price,
            'amount': position['amount'],
            'side': 'buy',
            'timestamp': datetime.now(),
            'profit': profit
        }
        return simulated_order, profit
    except Exception as e:
        print(f"Error simulating closing position for {symbol}: {e}")
        return None, 0

async def manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit):
    """
    열린 포지션을 관리하며, 각 포지션에 대해 알림을 발송하고,
    일정 횟수(여기서는 4회) 알림 후 시뮬레이션 청산을 진행하여 수익을 누적합니다.
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
                order, profit = close_position_simulation(exchange, position)
                simulated_total_profit += profit
                open_positions.remove(position)
                await log_and_notify(
                    f"포지션 청산: {position['symbol']} / 수익: {profit:.2f} USD / 누적 수익: {simulated_total_profit:.2f} USD",
                    telegram_token,
                    chat_id
                )
            except Exception as e:
                await log_and_notify(
                    f"{position['symbol']} 포지션 청산 오류: {e}",
                    telegram_token,
                    chat_id
                )
    return simulated_total_profit

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
    # 텔레그램 관련 설정 (토큰과 채팅 ID를 입력하세요)
    telegram_token = ""
    chat_id = ""

    # 바이낸스 API 키 (실제 매매가 아닌 시뮬레이션이므로, 꼭 사용하지 않아도 됩니다)
    api_key = ""
    api_secret = ""

    entry_amount_usd = 100  # 각 거래의 진입 금액 (USD 기준)
    num_candles = 7         # 이전 n개봉을 분석

    # 시뮬레이션 누적 수익 변수
    simulated_total_profit = 0

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
            # USDT 페어이면서 PERPETUAL(무기한) 계약인 심볼만 선택
            if symbol.endswith('USDT') and market['info']['contractType'] == 'PERPETUAL':
                # 예시: 'ZRO/USDT:USDT' -> 'ZRO/USDT'
                standardized_symbol = symbol.split(':')[0]
                binance_symbols.append(standardized_symbol)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")

    binance_symbols = list(set(binance_symbols))  # 중복 제거

    open_positions = []
    mismatched_symbols = []

    while True:
        start_time = datetime.now()
        next_run_time = start_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


        # 병렬 처리로 심볼 데이터 가져오기
        tasks = [process_symbol(symbol, exchange, num_candles=num_candles) for symbol in binance_symbols]
        results = await asyncio.gather(*tasks)

        trading_list = []

        for message, is_trading_candidate in results:
            if message:
                # 메시지의 첫 부분에서 심볼 이름 추출 (필요에 따라 파싱 방법 조정)
                symbol_name = message.split(' ')[0]
                if is_trading_candidate:
                    trading_list.append(symbol_name)
                else:
                    mismatched_symbols.append(symbol_name)

        # 시간 불일치 심볼 재검증
        resolved_symbols = await recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles)
        trading_list.extend(resolved_symbols)

        # 매매 대상 심볼 출력
        await log_and_notify(f"Trading candidates: {trading_list}", telegram_token, chat_id)

        # 추가 조건: 한 사이클에 매매 대상 코인이 15개 이상이면 신규 매수를 진행하지 않음
        if len(trading_list) >= 15:
            await log_and_notify(
                f"매매 대상 코인이 {len(trading_list)}개 발생하여 이번 사이클은 신규 매수를 진행하지 않습니다.",
                telegram_token,
                chat_id
            )
        else:
            # 매매 시뮬레이션: 각 거래 대상에 대해 숏 포지션 오픈
            for symbol in trading_list:
                order = open_short_position_simulation(exchange, symbol, entry_amount_usd, open_positions)
                if order:
                    await log_and_notify(f"Simulated short position opened for {symbol}: {order}", telegram_token, chat_id)

        # 열린 포지션 관리 (알림 횟수에 따라 시뮬레이션 청산 및 수익 계산)
        simulated_total_profit = await manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit)

        now = datetime.now()
        wait_time = (next_run_time - now).total_seconds()
        if wait_time > 0:
            await log_and_notify(f"Waiting {wait_time:.2f} seconds for the next cycle.", telegram_token, chat_id)
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    asyncio.run(main())
