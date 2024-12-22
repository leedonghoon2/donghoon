import requests
import time
import datetime
import hmac
import hashlib
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Binance API credentials
API_KEY = ""
API_SECRET = ""

# Telegram bot token and chat ID
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = "1496944404"

# Base URLs
BASE_URL = "https://fapi.binance.com"
UPBIT_URL = "https://api.upbit.com/v1"

# Trading configuration
BET_AMOUNT = 10  # Amount in USDT for each trade

# Telegram bot setup
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Helper functions for Binance API requests
def binance_signed_request(method, endpoint, params):
    query_string = "&".join([f"{key}={value}" for key, value in params.items()])
    signature = hmac.new(API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": API_KEY}
    url = f"{BASE_URL}{endpoint}?{query_string}&signature={signature}"

    if method == "POST":
        response = requests.post(url, headers=headers)
    elif method == "GET":
        response = requests.get(url, headers=headers)
    else:
        raise ValueError("지원되지 않는 요청 메서드입니다.")

    response.raise_for_status()
    return response.json()

def place_binance_order(ticker, action, amount):
    # Modify to handle short position logic
    if action == "SHORT":
        side = "SELL"  # 공매도 포지션 열기
    elif action == "CLOSE_SHORT":
        side = "BUY"  # 공매도 포지션 닫기
    else:
        raise ValueError("공매도 포지션에 대한 지원되지 않는 작업입니다.")

    params = {
        "symbol": f"{ticker}USDT",
        "side": side,
        "type": "MARKET",
        "quantity": amount,
        "timestamp": int(time.time() * 1000)
    }
    try:
        response = binance_signed_request("POST", "/fapi/v1/order", params)
        asyncio.run(send_telegram_message(f"{action} 주문이 성공적으로 실행되었습니다: {response}"))
    except Exception as e:
        asyncio.run(send_telegram_message(f"{ticker}에 대한 {action} 주문 오류: {e}"))

async def send_telegram_message(message):
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as e:
        print(f"텔레그램 메시지 전송 오류: {e}")

def get_upbit_krw_tickers():
    url = f"{UPBIT_URL}/market/all"
    response = requests.get(url)
    response.raise_for_status()

    markets = response.json()
    krw_tickers = [market['market'].replace("KRW-", "") for market in markets if market['market'].startswith("KRW-")]
    return krw_tickers

def get_binance_futures_tickers():
    url = f"{BASE_URL}/fapi/v1/exchangeInfo"
    response = requests.get(url)
    response.raise_for_status()

    symbols = response.json()['symbols']
    futures_tickers = [symbol['baseAsset'] for symbol in symbols]
    return futures_tickers

def find_common_tickers(upbit_tickers, binance_tickers):
    common_tickers = list(set(upbit_tickers) & set(binance_tickers))
    return common_tickers

def get_upbit_hourly_data(ticker):
    url = f"{UPBIT_URL}/candles/minutes/60?market=KRW-{ticker}&count=11"
    response = requests.get(url)
    if response.status_code == 200:
        candles = response.json()
        volumes = [candle['candle_acc_trade_volume'] for candle in candles]
        price_changes = [(candle['trade_price'] - candle['opening_price']) / candle['opening_price'] for candle in candles]
        return volumes, price_changes
    else:
        return [], []

def filter_tickers_by_conditions(tickers):
    significant_tickers = []

    for ticker in tickers:
        try:
            volumes, price_changes = get_upbit_hourly_data(ticker)
            if len(volumes) == 11 and len(price_changes) == 11:
                recent_volume = volumes[0]
                avg_volume = sum(volumes[1:]) / 10
                recent_price_change = price_changes[0]

                if recent_volume > 7 * avg_volume and recent_price_change > 0:
                    significant_tickers.append(ticker)

            time.sleep(0.1)  # API 호출 제한 방지를 위해 딜레이 추가
        except Exception as e:
            asyncio.run(send_telegram_message(f"티커 {ticker} 데이터 처리 중 오류 발생: {e}"))

    return significant_tickers

async def monitor_market():
    open_positions = {}

    # 시작 메시지 전송
    await send_telegram_message("자동 매매 봇이 시작되었습니다. 시장을 모니터링 중입니다...")

    while True:
        try:
            now = datetime.datetime.now()
            seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
            await send_telegram_message(f"다음 시간까지 대기 중... {seconds_until_next_hour}초")
            await asyncio.sleep(seconds_until_next_hour)

            # 매 시간 티커 데이터 가져오기
            upbit_tickers = get_upbit_krw_tickers()
            binance_tickers = get_binance_futures_tickers()

            common_tickers = find_common_tickers(upbit_tickers, binance_tickers)
            await send_telegram_message(f"공통 티커: {common_tickers}")

            # 조건 만족 티커 필터링
            significant_tickers = filter_tickers_by_conditions(common_tickers)

            await send_telegram_message(f"조건에 부합하는 티커: {significant_tickers}")

            # 조건 만족 티커 주문 실행
            for ticker in significant_tickers:
                if ticker not in open_positions:
                    open_positions[ticker] = []
                place_binance_order(ticker, "SHORT", BET_AMOUNT)  # 공매도 포지션 열기
                open_positions[ticker].append(now + datetime.timedelta(hours=3))

            # 3시간 후 포지션 청산 확인
            for ticker, close_times in list(open_positions.items()):
                for close_time in list(close_times):
                    if now >= close_time:
                        place_binance_order(ticker, "CLOSE_SHORT", BET_AMOUNT)  # 공매도 포지션 닫기
                        close_times.remove(close_time)
                if not close_times:
                    del open_positions[ticker]

            # 현재 포지션 정보 전송
            await send_telegram_message(f"현재 포지션: {open_positions}")

        except Exception as e:
            await send_telegram_message(f"시스템 오류 발생: {e}")

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(monitor_market())
    except Exception as e:
        asyncio.run(send_telegram_message(f"프로그램 실행 중 치명적 오류 발생: {e}"))
