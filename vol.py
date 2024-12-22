import requests
import time
import datetime
import hmac
import hashlib
import json

# Binance API credentials
API_KEY = "your_api_key_here"
API_SECRET = "your_api_secret_here"

BASE_URL = "https://fapi.binance.com"

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
        raise ValueError("Unsupported method")

    response.raise_for_status()
    return response.json()

def place_binance_order(ticker, action, amount):
    side = "BUY" if action == "BUY" else "SELL"
    params = {
        "symbol": f"{ticker}USDT",
        "side": side,
        "type": "MARKET",
        "quantity": amount,
        "timestamp": int(time.time() * 1000)
    }
    try:
        response = binance_signed_request("POST", "/fapi/v1/order", params)
        print(f"{action} order placed: {response}")
    except requests.exceptions.RequestException as e:
        print(f"Error placing {action} order for {ticker}: {e}")

def get_upbit_krw_tickers():
    url = "https://api.upbit.com/v1/market/all"
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

def get_binance_hourly_data(ticker):
    url = f"{BASE_URL}/fapi/v1/klines?symbol={ticker}USDT&interval=1h&limit=11"
    response = requests.get(url)
    if response.status_code == 200:
        klines = response.json()
        volumes = [float(kline[7]) for kline in klines]
        price_changes = [(float(kline[4]) - float(kline[1])) / float(kline[1]) for kline in klines]
        return volumes, price_changes
    else:
        return [], []

def filter_tickers_by_conditions(tickers):
    significant_tickers = []

    for ticker in tickers:
        volumes, price_changes = get_binance_hourly_data(ticker)
        if len(volumes) == 11 and len(price_changes) == 11:
            recent_volume = volumes[-1]
            avg_volume = sum(volumes[:-1]) / 10
            recent_price_change = price_changes[-1]

            if recent_volume > 7 * avg_volume and recent_price_change > 0:
                significant_tickers.append(ticker)

        time.sleep(0.1)  # To avoid hitting the API rate limit

    return significant_tickers

def main():
    open_positions = {}

    while True:
        try:
            now = datetime.datetime.now()
            seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
            print(f"Waiting for the next hour... {seconds_until_next_hour} seconds")
            time.sleep(seconds_until_next_hour)

            # Fetch tickers every hour
            upbit_tickers = get_upbit_krw_tickers()
            binance_tickers = get_binance_futures_tickers()

            common_tickers = find_common_tickers(upbit_tickers, binance_tickers)
            print(f"Common tickers: {common_tickers}")

            # Filter tickers by conditions every hour
            significant_tickers = filter_tickers_by_conditions(common_tickers)

            print("Tickers meeting the conditions:")
            print(significant_tickers)

            # Place orders for significant tickers
            for ticker in significant_tickers:
                if ticker not in open_positions:
                    open_positions[ticker] = []
                place_binance_order(ticker, "BUY", 10)
                open_positions[ticker].append(now + datetime.timedelta(hours=3))

            # Check and close positions after 3 hours
            for ticker, close_times in list(open_positions.items()):
                for close_time in list(close_times):
                    if now >= close_time:
                        place_binance_order(ticker, "SELL", 10)
                        close_times.remove(close_time)
                if not close_times:
                    del open_positions[ticker]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")

if __name__ == "__main__":
    main()
