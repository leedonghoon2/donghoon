import asyncio
import ccxt.async_support as ccxt  # 비동기 버전 사용
from datetime import datetime, timedelta
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

# 타임프레임 문자열(e.g. '1m', '5m', '1h', '1d')를 timedelta로 변환하는 함수
def get_timeframe_timedelta(timeframe_str):
    try:
        num = int(timeframe_str[:-1])
    except ValueError:
        num = 1
    unit = timeframe_str[-1].lower()
    if unit == 'm':
        return timedelta(minutes=num)
    elif unit == 'h':
        return timedelta(hours=num)
    elif unit == 'd':
        return timedelta(days=num)
    else:
        return timedelta(minutes=1)

# 비동기 방식으로 Binance 캔들 데이터를 가져오는 함수 (rate limit 에러 처리 포함)
async def fetch_binance_candles(exchange, symbol, timeframe, limit=12, semaphore=None, telegram_token="", chat_id=""):
    while True:
        try:
            async with semaphore:
                candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return candles
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching candles: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error fetching candles for {symbol}: {e}")
                return []

# 캔들 데이터를 분석하는 함수 (동기 함수)
def analyze_candles(candles, num_candles):
    if len(candles) < num_candles + 2:
        return None, None, None, None, []
    target_candle = candles[-2]  # 선택된 타임프레임의 직전 캔들
    previous_candles = candles[-(num_candles + 2):-2]
    previous_volumes = [candle[5] for candle in previous_candles]
    average_volume = sum(previous_volumes) / len(previous_volumes)
    volume_threshold = 3 * average_volume  # 조건 배수 (원하는 배수로 조정 가능)
    target_volume = target_candle[5]
    opening_price = target_candle[1]
    closing_price = target_candle[4]
    target_change = (closing_price - opening_price) / opening_price * 100
    return target_volume, average_volume, volume_threshold, target_change, previous_volumes

# 각 심볼의 캔들 데이터를 처리하는 비동기 함수 (실제 전략 판단용)
async def process_symbol(symbol, exchange, num_candles, timeframe, semaphore, telegram_token, chat_id):
    candles = await fetch_binance_candles(
        exchange, symbol, timeframe, limit=num_candles + 2,
        semaphore=semaphore, telegram_token=telegram_token, chat_id=chat_id
    )
    if not candles:
        return None, None
    target_volume, average_volume, volume_threshold, target_change, previous_volumes = analyze_candles(candles, num_candles)
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

# 실제 거래: 숏 포지션 진입 (시장 주문, SELL 주문)
async def open_short_position(exchange, symbol, margin_usd, open_positions, semaphore, telegram_token, chat_id):
    # 우선 현재 가격 조회
    while True:
        try:
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Rate limit reached for {symbol} while fetching ticker for opening position: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                await log_and_notify(f"Error fetching ticker for {symbol}: {e}", telegram_token, chat_id)
                return None

    price = ticker['last']
    amount = margin_usd / price  # 산출된 수량(실제 거래 시 레버리지 및 계약 단위를 고려해야 함)
    
    # 실제 주문 실행 (시장 SELL 주문)
    while True:
        try:
            async with semaphore:
                order = await exchange.create_order(symbol, 'market', 'sell', amount, None)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Rate limit reached for {symbol} while creating order for opening position: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                await log_and_notify(f"Error creating order for {symbol}: {e}", telegram_token, chat_id)
                return None

    fee_open = margin_usd * 0.0004  # 실제 거래 수수료는 거래소에 따라 다를 수 있음
    # 포지션 정보를 개별적으로 저장
    open_positions.append({
        'symbol': symbol,
        'opened_at': datetime.now(),
        'open_price': price,
        'margin': margin_usd,
        'amount': amount,
        'order': order,
        'open_fee': fee_open,
        'alert_count': 0
    })
    return order, fee_open

# 실제 거래: 포지션 청산 (시장 주문, BUY 주문)
async def close_position(exchange, position, semaphore, telegram_token, chat_id):
    symbol = position['symbol']
    while True:
        try:
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Rate limit reached for {symbol} while fetching ticker for closing position: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                await log_and_notify(f"Error fetching ticker for {symbol}: {e}", telegram_token, chat_id)
                return None, 0, 0

    current_price = ticker['last']
    open_price = position['open_price']
    amount = position['amount']
    # 숏 포지션의 경우, 가격이 하락하면 수익이 발생하므로 계산은 (open_price - current_price)
    profit = (open_price - current_price) * amount

    # 실제 주문 실행 (시장 BUY 주문으로 청산)
    while True:
        try:
            async with semaphore:
                order = await exchange.create_order(symbol, 'market', 'buy', amount, None)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Rate limit reached for {symbol} while creating order for closing position: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                await log_and_notify(f"Error creating order for {symbol}: {e}", telegram_token, chat_id)
                return None, 0, 0

    fee_close = (current_price * amount) * 0.0004
    return order, profit, fee_close

# 열린 포지션 관리 함수 (실제 거래, 개별 포지션 청산)
async def manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit, total_seed, accumulated_fee, semaphore):
    for position in open_positions[:]:
        position['alert_count'] += 1
        await log_and_notify(
            f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.",
            telegram_token,
            chat_id
        )
        # 예를 들어, 4회 이상 알림 후 청산하도록 설정 (전략에 맞게 조정 가능)
        if position['alert_count'] >= 4:
            try:
                order, profit, fee_close = await close_position(exchange, position, semaphore, telegram_token, chat_id)
                simulated_total_profit += profit
                accumulated_fee += fee_close  # 청산 시 발생한 수수료 누적
                open_positions.remove(position)
                profit_rate = (simulated_total_profit / total_seed) * 100  # 누적 수익률 계산 (전체 시드 기준)
                await log_and_notify(
                    f"포지션 청산: {position['symbol']} / 수익: {profit:.2f} USD / 누적 수익: {simulated_total_profit:.2f} USD / "
                    f"누적 수익률: {profit_rate:.2f}% / 누적 수수료: {accumulated_fee:.4f} USD",
                    telegram_token,
                    chat_id
                )
            except Exception as e:
                await log_and_notify(
                    f"{position['symbol']} 포지션 청산 오류: {e}",
                    telegram_token,
                    chat_id
                )
    return simulated_total_profit, accumulated_fee

# 시간 불일치 심볼 재검증 함수 (비동기, rate limit 처리 포함)
async def recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles, timeframe, semaphore, telegram_token, chat_id):
    valid_symbols = []
    for symbol in mismatched_symbols[:]:
        candles = await fetch_binance_candles(
            exchange, symbol, timeframe, limit=num_candles+2,
            semaphore=semaphore, telegram_token=telegram_token, chat_id=chat_id
        )
        if candles:
            target_volume, average_volume, volume_threshold, target_change, _ = analyze_candles(candles, num_candles)
            if target_volume >= volume_threshold and target_change > 0:
                valid_symbols.append(symbol)
    return valid_symbols

async def main():
    # 텔레그램 관련 설정 (토큰과 채팅 ID 입력)
    telegram_token = ""  # 여기에 텔레그램 봇 토큰 입력
    chat_id = ""         # 여기에 채팅 ID 입력
    
    # 바이낸스 API 키 (실제 매매용)
    api_key = ""
    api_secret = ""
    
    entry_amount_usd = 100    # 거래당 진입 금액 (USD)
    num_candles = 7           # 분석할 캔들 개수
    total_seed = 300          # 전체 시드 (초기 투자금)
    
    # 원하는 타임프레임 설정 (예: '1h' -> 매 정각에 거래)
    candle_timeframe = '1h'
    
    simulated_total_profit = 0
    accumulated_fee = 0       # 누적 수수료 변수 초기화
    
    # ***** 최초 실행 시간을 설정하는 부분 *****
    initial_start_str = "2023-12-31 14:00:00"  
    if initial_start_str:
        initial_start_time = datetime.strptime(initial_start_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if now < initial_start_time:
            wait_time = (initial_start_time - now).total_seconds()
            await log_and_notify(
                f"최초 실행 시각까지 {wait_time:.2f}초 대기합니다. (최초 실행 시각: {initial_start_time.strftime('%Y-%m-%d %H:%M:%S')})",
                telegram_token,
                chat_id
            )
            await asyncio.sleep(wait_time)
    now = datetime.now()
    cycle_start = now.replace(minute=0, second=0, microsecond=0)
    await log_and_notify(f"최초 사이클 시작 시각: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
    
    # 바이낸스 선물 클라이언트 초기화 (비동기, enableRateLimit 옵션 포함)
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })
    await exchange.load_markets()
    
    binance_symbols = []
    for symbol in exchange.symbols:
        try:
            market = exchange.market(symbol)
            if symbol.endswith('USDT') and market['info'].get('contractType') == 'PERPETUAL':
                standardized_symbol = symbol.split(':')[0]
                binance_symbols.append(standardized_symbol)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")
    binance_symbols = list(set(binance_symbols))
    
    open_positions = []
    mismatched_symbols = []
    
    # 동시에 실행되는 API 호출 수를 제한하기 위한 semaphore (예: 최대 10개)
    semaphore = asyncio.Semaphore(10)
    
    while True:
        await log_and_notify(f"사이클 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
        
        # 각 심볼의 캔들 데이터를 병렬로 처리 (비동기, semaphore, telegram 정보 전달)
        tasks = [
            process_symbol(symbol, exchange, num_candles, candle_timeframe, semaphore, telegram_token, chat_id)
            for symbol in binance_symbols
        ]
        results = await asyncio.gather(*tasks)
        
        trading_list = []
        for result in results:
            if result is None:
                continue
            message, is_trading_candidate = result
            if message:
                symbol_name = message.split(' ')[0]
                if is_trading_candidate:
                    trading_list.append(symbol_name)
                else:
                    mismatched_symbols.append(symbol_name)
        
        # 시간 불일치 심볼 재검증 (비동기, semaphore 및 telegram 정보 전달)
        resolved_symbols = await recheck_mismatched_symbols(
            mismatched_symbols, exchange, num_candles, candle_timeframe, semaphore, telegram_token, chat_id
        )
        trading_list.extend(resolved_symbols)
        
        # 거래 후보 리스트 중복 제거 (순서 유지)
        trading_list = list(dict.fromkeys(trading_list))
        
        await log_and_notify(f"Trading candidates: {trading_list}", telegram_token, chat_id)
        
        # 한 사이클에 거래 후보가 15개 이상이면 신규 매수 진행하지 않음
        if len(trading_list) >= 15:
            await log_and_notify(
                f"매매 대상 코인이 {len(trading_list)}개 발생하여 이번 사이클은 신규 매수를 진행하지 않습니다.",
                telegram_token,
                chat_id
            )
        else:
            for symbol in trading_list:
                result = await open_short_position(exchange, symbol, entry_amount_usd, open_positions, semaphore, telegram_token, chat_id)
                if result:
                    order, fee_open = result
                    accumulated_fee += fee_open  # 포지션 오픈 시 발생한 수수료 누적
                    await log_and_notify(
                        f"실제 숏 포지션 오픈 - {symbol}: {order}. Open fee: {fee_open:.4f} USD / 누적 수수료: {accumulated_fee:.4f} USD",
                        telegram_token,
                        chat_id
                    )
        
        # 열린 포지션 관리 (청산 및 누적 수익, 누적 수수료 업데이트)
        simulated_total_profit, accumulated_fee = await manage_open_positions(
            open_positions, exchange, telegram_token, chat_id,
            simulated_total_profit, total_seed, accumulated_fee, semaphore
        )
        
        # 사이클 끝나면 mismatched_symbols 초기화
        mismatched_symbols.clear()
        
        # 다음 사이클을 매 정각에 시작하도록 계산
        now = datetime.now()
        next_run_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        wait_time = (next_run_time - now).total_seconds()
        await log_and_notify(
            f"다음 사이클까지 {wait_time:.2f}초 대기합니다. (다음 실행 시각: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')})",
            telegram_token,
            chat_id
        )
        await asyncio.sleep(wait_time)
    
    # 무한 루프이므로 종료 시 exchange 연결 정리(필요시)
    # await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
