import asyncio
import ccxt
from datetime import datetime, timedelta
import aiohttp
import math

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

# 바이낸스에서 캔들 데이터를 가져오는 함수
def fetch_binance_candles(exchange, symbol, timeframe, limit=12):
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return candles
    except Exception as e:
        print(f"Error fetching candles for {symbol}: {e}")
        return []

# 캔들 데이터를 분석하는 함수
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

# 심볼 당 캔들 데이터 처리 함수 (타임프레임 인자 포함)
async def process_symbol(symbol, exchange, num_candles, timeframe):
    candles = fetch_binance_candles(exchange, symbol, timeframe, limit=num_candles + 2)
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

# 매매 시뮬레이션: 숏 포지션 오픈 (매수 시 수수료 0.04% 적용)
def open_short_position_simulation(exchange, symbol, margin_usd, open_positions):
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
        # 매수(포지션 오픈) 시 수수료 계산: 주문금액 * 0.0004
        fee_open = margin_usd * 0.0004
        open_positions.append({
            'symbol': symbol,
            'opened_at': datetime.now(),
            'open_price': price,
            'margin': margin_usd,
            'amount': amount,
            'alert_count': 0,
            'order': simulated_order,
            'open_fee': fee_open
        })
        return simulated_order, fee_open
    except Exception as e:
        print(f"Error simulating opening position for {symbol}: {e}")
        return None

# 매매 시뮬레이션: 포지션 청산 (매도 시 수수료 0.04% 적용)
def close_position_simulation(exchange, position):
    try:
        symbol = position['symbol']
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        open_price = position['open_price']
        # 숏 포지션의 경우, (개시가 - 청산가) * 수량이 수익
        profit = (open_price - current_price) * position['amount']
        simulated_order = {
            'symbol': symbol,
            'price': current_price,
            'amount': position['amount'],
            'side': 'buy',
            'timestamp': datetime.now(),
            'profit': profit
        }
        # 매도(포지션 청산) 시 수수료 계산: 청산 주문 금액 (현재가 * 수량) * 0.0004
        fee_close = (current_price * position['amount']) * 0.0004
        return simulated_order, profit, fee_close
    except Exception as e:
        print(f"Error simulating closing position for {symbol}: {e}")
        return None, 0, 0

# 열린 포지션 관리 함수 (수수료 누적 금액 업데이트 포함)
async def manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit, total_seed, accumulated_fee):
    for position in open_positions[:]:
        position['alert_count'] += 1
        await log_and_notify(
            f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.",
            telegram_token,
            chat_id
        )
        if position['alert_count'] >= 4:
            try:
                order, profit, fee_close = close_position_simulation(exchange, position)
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

# 시간 불일치 심볼 재검증 함수 (타임프레임 인자 포함)
async def recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles, timeframe):
    valid_symbols = []
    for symbol in mismatched_symbols[:]:
        candles = fetch_binance_candles(exchange, symbol, timeframe, limit=num_candles+2)
        if candles:
            target_volume, average_volume, volume_threshold, target_change, _ = analyze_candles(candles, num_candles)
            if target_volume >= volume_threshold and target_change > 0:
                valid_symbols.append(symbol)
    return valid_symbols

async def main():
    # 텔레그램 관련 설정 (토큰과 채팅 ID 입력)
    telegram_token = ""
    chat_id = ""
    
    # 바이낸스 API 키 (시뮬레이션용)
    api_key = ""
    api_secret = ""
    
    entry_amount_usd = 100    # 거래당 진입 금액 (USD)
    num_candles = 7           # 분석할 캔들 개수
    total_seed = 1000         # 전체 시드 (초기 투자금)
    
    # 원하는 타임프레임 설정: 예) '1m' -> 1분봉, '5m' -> 5분봉, '1h' -> 1시간봉, '1d' -> 1일봉 등
    candle_timeframe = '5m'   # 여기서 원하는 타임프레임으로 변경 가능
    delta = get_timeframe_timedelta(candle_timeframe)
    
    simulated_total_profit = 0
    accumulated_fee = 0       # 누적 수수료 변수 초기화
    
    # ***** 최초 실행 시간을 설정하는 부분 *****
    # 아래 initial_start_str 값을 원하는 최초 실행 시각("YYYY-MM-DD HH:MM:SS")으로 설정합니다.
    # 예를 들어 "2023-12-31 14:05:00"과 같이 설정할 수 있습니다.
    initial_start_str = "2023-12-31 14:05:00"  
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
    else:
        initial_start_time = datetime.now()
    # 최초 사이클 기준 시작 시각을 설정
    cycle_start = initial_start_time
    await log_and_notify(f"최초 사이클 시작 시각: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
    
    # 바이낸스 선물 클라이언트 초기화
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })
    exchange.load_markets()
    
    binance_symbols = []
    for symbol in exchange.symbols:
        try:
            market = exchange.market(symbol)
            if symbol.endswith('USDT') and market['info']['contractType'] == 'PERPETUAL':
                standardized_symbol = symbol.split(':')[0]
                binance_symbols.append(standardized_symbol)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")
    # 중복 제거
    binance_symbols = list(set(binance_symbols))
    
    open_positions = []
    mismatched_symbols = []
    
    while True:
        # 각 사이클 시작 시, 기준 시각은 cycle_start로 고정되어 있습니다.
        await log_and_notify(f"사이클 시작 시각: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
        
        # 각 심볼의 캔들 데이터를 병렬로 처리 (타임프레임 적용)
        tasks = [process_symbol(symbol, exchange, num_candles, candle_timeframe) for symbol in binance_symbols]
        results = await asyncio.gather(*tasks)
        
        trading_list = []
        for message, is_trading_candidate in results:
            if message:
                symbol_name = message.split(' ')[0]
                if is_trading_candidate:
                    trading_list.append(symbol_name)
                else:
                    mismatched_symbols.append(symbol_name)
        
        # 시간 불일치 심볼 재검증 (타임프레임 적용)
        resolved_symbols = await recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles, candle_timeframe)
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
                result = open_short_position_simulation(exchange, symbol, entry_amount_usd, open_positions)
                if result:
                    order, fee_open = result
                    accumulated_fee += fee_open  # 포지션 오픈 시 발생한 수수료 누적
                    await log_and_notify(
                        f"Simulated short position opened for {symbol}: {order}. Open fee: {fee_open:.4f} USD / 누적 수수료: {accumulated_fee:.4f} USD",
                        telegram_token,
                        chat_id
                    )
        
        # 열린 포지션 관리 (청산 및 누적 수익, 누적 수수료 업데이트)
        simulated_total_profit, accumulated_fee = await manage_open_positions(
            open_positions, exchange, telegram_token, chat_id,
            simulated_total_profit, total_seed, accumulated_fee
        )
        
        # 다음 사이클의 실행 시각은 현재 사이클의 기준 시작 시각(cycle_start)에 delta를 더한 값
        next_run_time = cycle_start + delta
        now = datetime.now()
        wait_time = (next_run_time - now).total_seconds()
        if wait_time > 0:
            await log_and_notify(
                f"다음 사이클까지 {wait_time:.2f}초 대기합니다. (다음 실행 시각: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')})",
                telegram_token,
                chat_id
            )
            await asyncio.sleep(wait_time)
        else:
            await log_and_notify("대기 시간보다 작업에 소요된 시간이 길어 즉시 다음 사이클을 시작합니다.", telegram_token, chat_id)
        
        # 다음 사이클의 기준 시작 시각을 갱신 (고정 주기)
        cycle_start = next_run_time

if __name__ == "__main__":
    asyncio.run(main())
