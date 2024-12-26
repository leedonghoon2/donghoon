import time
import requests
from tqdm import tqdm
from datetime import datetime, timedelta
import ccxt
import asyncio
import aiohttp
import pandas as pd

async def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {"chat_id": chat_id, "text": message}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"텔레그램 메시지 전송 실패: {response.status}")

async def log_and_notify(message, telegram_token, chat_id):
    print(message)
    await send_telegram_message(telegram_token, chat_id, message)

def get_binance_futures_symbols():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        futures_symbols = {symbol['baseAsset'] for symbol in data['symbols']}
        return futures_symbols
    except Exception as e:
        print(f"오류 발생: {e}")
        return set()

def get_upbit_krw_symbols():
    try:
        url = "https://api.upbit.com/v1/market/all"
        response = requests.get(url)
        response.raise_for_status()
        markets = response.json()
        krw_symbols = {market['market'].split('-')[1] for market in markets if market['market'].startswith('KRW-')}
        return krw_symbols
    except Exception as e:
        print(f"오류 발생: {e}")
        return set()

def fetch_candles(market, minutes=60, count=200, to=None):
    url = f"https://api.upbit.com/v1/candles/minutes/{minutes}"
    params = {"market": market, "count": count}
    if to:
        params["to"] = to
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_previous_hour_candles(symbol, count=200, telegram_token=None, chat_id=None):
    try:
        now = datetime.now()
        market = f"KRW-{symbol}"
        all_data = []
        next_time = None

        for _ in range(2):  # Adjust the range to fetch more data if needed
            data = fetch_candles(market, minutes=60, count=count, to=next_time)
            if not data:
                break
            all_data.extend(data)
            next_time = data[-1]['candle_date_time_utc']

        all_data = sorted(all_data, key=lambda x: x['candle_date_time_utc'], reverse=True)

        if len(all_data) < 12:
            error_message = f"{symbol} 데이터 부족: {len(all_data)}개 반환됨"
            print(error_message)
            if telegram_token and chat_id:
                asyncio.create_task(send_telegram_message(telegram_token, chat_id, error_message))
            return None, [], 0, 0, 0

        target_candle = all_data[1]  # H-1 기준
        previous_candles = all_data[2:12]  # 이전 10개 봉

        previous_volumes = [candle['candle_acc_trade_volume'] for candle in previous_candles]
        target_volume = target_candle['candle_acc_trade_volume']
        average_volume = sum(previous_volumes) / len(previous_volumes)
        volume_threshold = 7 * average_volume
        target_change = (target_candle['trade_price'] - target_candle['opening_price']) / target_candle['opening_price'] * 100

        message = (
            f"{symbol} 기준봉 정보:\n"
            f"- 시간: {target_candle['candle_date_time_kst']}\n"
            f"- 거래량: {target_volume}\n"
            f"- 변동률: {target_change:.2f}%\n"
            f"- 이전 10개봉 거래량 리스트: {previous_volumes}\n"
            f"- 이전 10개봉 평균 거래량: {average_volume}\n"
            f"- 평균 거래량의 7배값: {volume_threshold}"
        )
        print(message)
        if telegram_token and chat_id:
            asyncio.create_task(send_telegram_message(telegram_token, chat_id, message))

        return target_volume, previous_volumes, average_volume, volume_threshold, target_change
    except Exception as e:
        error_message = f"{symbol} 캔들 데이터 가져오기 오류: {e}"
        print(error_message)
        if telegram_token and chat_id:
            asyncio.create_task(send_telegram_message(telegram_token, chat_id, error_message))
        return None, [], 0, 0, 0

def open_short_position(exchange, symbol, margin_usd, open_positions):
    try:
        exchange.load_markets()
        market = exchange.market(symbol)
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
            'amount': amount,  # 추가: 매수된 수량 저장
            'alert_count': 0
        })
        return order
    except Exception as e:
        print(f"{symbol} 포지션 열기 오류: {e}")
        return None

def close_position(exchange, position):
    try:
        symbol = position['symbol']
        amount = position['amount']  # 포지션에 저장된 개별 수량만 청산
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=amount
        )
        return order
    except Exception as e:
        print(f"{symbol} 포지션 청산 오류: {e}")
        return None

async def main():
    telegram_token = ""
    chat_id = ""

    api_key = ''
    api_secret = ''

    entry_amount_usd = 100

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    exchange.load_markets()

    binance_symbols = get_binance_futures_symbols()
    upbit_symbols = get_upbit_krw_symbols()

    common_symbols = binance_symbols & upbit_symbols
    await log_and_notify(f"교집합 심볼 발견: {len(common_symbols)}개 심볼.", telegram_token, chat_id)

    open_positions = []

    while True:
        start_time = datetime.now()
        next_run_time = (start_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        trading_list = []

        for symbol in tqdm(sorted(common_symbols), desc="심볼 처리 중"):
            target_volume, previous_volumes, average_volume, volume_threshold, target_change = get_previous_hour_candles(symbol, telegram_token=telegram_token, chat_id=chat_id)
            if target_volume and len(previous_volumes) == 10:
                if target_volume >= volume_threshold and target_change > 0:
                    trading_list.append(symbol)
            await asyncio.sleep(0.2)

        await log_and_notify(f"매매 대상 코인: {trading_list}", telegram_token, chat_id)

        for symbol in trading_list:
            binance_symbol = f"{symbol}USDT"
            order = open_short_position(exchange, binance_symbol, entry_amount_usd, open_positions)
            if order:
                await log_and_notify(f"{binance_symbol} 숏 포지션 열림: {order}", telegram_token, chat_id)

        for position in open_positions[:]:
            position['alert_count'] += 1
            if position['alert_count'] == 4:
                order = close_position(exchange, position)
                if order:
                    await log_and_notify(f"{position['symbol']} 포지션 청산됨: {order}", telegram_token, chat_id)
                open_positions.remove(position)
            else:
                await log_and_notify(f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.", telegram_token, chat_id)

        now = datetime.now()
        wait_time = (next_run_time - now).total_seconds()
        if wait_time > 0:
            await log_and_notify(f"다음 사이클까지 {wait_time:.2f}초 대기 중.", telegram_token, chat_id)
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    asyncio.run(main())
