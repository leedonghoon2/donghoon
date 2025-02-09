import asyncio
import ccxt.async_support as ccxt  # 비동기 버전 사용
from datetime import datetime, timedelta
import aiohttp
import matplotlib.pyplot as plt
from io import BytesIO

# 누적 수익 데이터를 기록할 리스트
# 각 항목은 (시간, 누적 수익 (USD)) 형식입니다.
profit_history = []

# 텔레그램 메시지 전송 함수
async def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {"chat_id": chat_id, "text": message}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"Telegram message failed: {response.status}")

# 텔레그램 사진(그래프) 전송 함수
async def send_telegram_photo(token, chat_id, photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", chat_id)
    data.add_field("caption", caption)
    data.add_field("photo", photo_bytes, filename="profit_graph.png", content_type="image/png")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.post(url, data=data) as response:
            if response.status != 200:
                print(f"Failed to send photo: {response.status}")

async def log_and_notify(message, telegram_token, chat_id):
    print(message)
    await send_telegram_message(telegram_token, chat_id, message)

# 누적 수익률 그래프 생성 및 전송 함수
async def send_profit_graph(telegram_token, chat_id):
    if not profit_history:
        await send_telegram_message(telegram_token, chat_id, "누적 수익 데이터가 없습니다.")
        return

    # profit_history의 데이터 분리: 시간, 수익
    times, profits = zip(*profit_history)
    plt.figure(figsize=(10, 5))
    plt.plot(times, profits, marker='o')
    plt.title("누적 수익률")
    plt.xlabel("시간")
    plt.ylabel("누적 수익 (USD)")
    plt.grid(True)
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    await send_telegram_photo(telegram_token, chat_id, buf.read(), caption="누적 수익률 그래프")

# 텔레그램 업데이트(메시지)를 폴링하는 함수
async def poll_telegram_updates(telegram_token, chat_id):
    last_update_id = None
    while True:
        url = f"https://api.telegram.org/bot{telegram_token}/getUpdates"
        params = {}
        if last_update_id is not None:
            params["offset"] = last_update_id + 1
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ok"):
                            for update in data.get("result", []):
                                last_update_id = update["update_id"]
                                if "message" in update:
                                    text = update["message"].get("text", "")
                                    if text.strip() == "수익률 확인":
                                        await send_profit_graph(telegram_token, chat_id)
        except Exception as e:
            print("Error in poll_telegram_updates:", e)
        await asyncio.sleep(5)  # 5초마다 폴링

# -------------------------------
# 이하부터 기존 시뮬레이션 거래 코드
# -------------------------------

# 타임프레임 문자열(e.g. '1m', '5m', '1h', '1d')를 timedelta로 변환
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

# 각 심볼의 캔들 데이터를 처리하는 함수 (telegram token, chat_id 전달)
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

# 비동기 방식: 숏 포지션 오픈 시뮬레이션 (rate limit 처리 포함)
async def open_short_position_simulation(exchange, symbol, margin_usd, open_positions, semaphore, telegram_token, chat_id):
    while True:
        try:
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching ticker (open position): {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error simulating opening position for {symbol}: {e}")
                return None
    price = ticker['last']
    amount = margin_usd / price
    simulated_order = {
        'symbol': symbol,
        'price': price,
        'amount': amount,
        'side': 'sell',
        'timestamp': datetime.now()
    }
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

# 비동기 방식: 포지션 청산 시뮬레이션 (rate limit 처리 포함)
async def close_position_simulation(exchange, position, semaphore, telegram_token, chat_id):
    while True:
        try:
            symbol = position['symbol']
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching ticker (close position): {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error simulating closing position for {symbol}: {e}")
                return None, 0, 0
    current_price = ticker['last']
    open_price = position['open_price']
    profit = (open_price - current_price) * position['amount']
    simulated_order = {
        'symbol': symbol,
        'price': current_price,
        'amount': position['amount'],
        'side': 'buy',
        'timestamp': datetime.now(),
        'profit': profit
    }
    fee_close = (current_price * position['amount']) * 0.0004
    return simulated_order, profit, fee_close

# 열린 포지션 관리 함수 (비동기, rate limit 처리 포함)
async def manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit, total_seed, accumulated_fee, semaphore):
    for position in open_positions[:]:
        position['alert_count'] += 1
        await log_and_notify(
            f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.",
            telegram_token,
            chat_id
        )
        if position['alert_count'] >= 4:
            try:
                order, profit, fee_close = await close_position_simulation(exchange, position, semaphore, telegram_token, chat_id)
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
    
    # 바이낸스 API 키 (시뮬레이션용)
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
            wait_time = (initial_start
