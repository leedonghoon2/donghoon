import requests
import pandas as pd
from prophet import Prophet
import time
import matplotlib.pyplot as plt
from matplotlib import rc
from tqdm import tqdm
import telegram ## pip install python-telegram-bot
import asyncio

# 한글 폰트 설정
rc('font', family='AppleGothic')  # Mac에서는 'AppleGothic', Windows는 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False  # 음수 기호 깨짐 방지

# 설정 변수
CANDLE_MINUTES = 5  # 몇 분봉 데이터를 가져올지 설정
REFRESH_INTERVAL = CANDLE_MINUTES * 60  # 새로고침 시간 (초 단위)

# Upbit API URL
BASE_URL = "https://api.upbit.com/v1/candles/minutes/"
MARKET_URL = "https://api.upbit.com/v1/market/all"

# 전역 변수
WIN_COUNT = 0  # 승 누적
LOSS_COUNT = 0  # 패 누적
PREVIOUS_TOP_GAINERS = []  # 이전 상승률 상위 5개 코인

token = '6277404128:AAGoL8YfdkfRLRrt8OeOxBuIPwFgwRuOkjI'
chat_id = '1496944404'
timesleep = 0

async def main_시작():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "테스트를 시작합니다...")
            break        
        except:
            await asyncio.sleep(timesleep)
            continue

async def main_집계():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"승 = {WIN_COUNT}\n패 = {LOSS_COUNT}")
            break        
        except:
            await asyncio.sleep(timesleep)
            continue

asyncio.run(main_시작())

def fetch_all_markets():
    url = MARKET_URL
    response = requests.get(url)
    if response.status_code == 200:
        markets = response.json()
        return [market['market'] for market in markets if market['market'].startswith('KRW-')]
    else:
        raise Exception(f"오류 {response.status_code}: {response.text}")

def fetch_candles(market, minutes=CANDLE_MINUTES, count=200, to=None):
    url = f"{BASE_URL}{minutes}"
    params = {
        "market": market,
        "count": count
    }
    if to:
        params["to"] = to
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"오류 {response.status_code}: {response.text}")

def get_recent_1000_candles(market, minutes=CANDLE_MINUTES):
    all_data = []
    next_time = None
    for _ in tqdm(range(3), desc=f"{market} 데이터 가져오는 중", unit="batch"):  # 5 * 200 = 1000개 데이터 가져오기
        data = fetch_candles(market=market, minutes=minutes, count=200, to=next_time)
        if not data:
            break
        all_data.extend(data)
        next_time = data[-1]['candle_date_time_utc']  # 마지막 캔들의 시간
        time.sleep(0.1)  # 200ms 대기 (Rate Limit 방지)
    return all_data

def fetch_and_predict_for_all():
    # 전체 코인 목록 가져오기
    print("모든 시장 가져오는 중...")
    markets = fetch_all_markets()

    results = {}
    with tqdm(total=len(markets), desc="전체 진행률", unit="시장") as overall_progress:
        for market in markets:
            print(f"{market} 처리 중...")
            try:
                candles = get_recent_1000_candles(market=market)
                df = pd.DataFrame(candles)
                df = df[["candle_date_time_kst", "trade_price"]]
                df.columns = ["ds", "y"]

                # 날짜 변환
                df['ds'] = pd.to_datetime(df['ds'])

                # Prophet 모델 학습 및 예측
                model = Prophet()
                model.fit(df)
                future = model.make_future_dataframe(periods=72, freq=f'{CANDLE_MINUTES}min')
                forecast = model.predict(future)

                # 날짜 변환
                forecast['ds'] = pd.to_datetime(forecast['ds'])

                results[market] = {
                    "forecast": forecast,
                    "current_price": candles[0]['trade_price'],  # 가장 마지막 캔들 데이터의 가격
                    "previous_price": candles[1]['trade_price'],  # 마지막 바로 이전 캔들 데이터의 가격
                    "df": df  # 원본 데이터 저장
                }
            except Exception as e:
                print(f"{market} 처리 중 오류 발생: {e}")
            finally:
                overall_progress.update(1)
    return results

def evaluate_top_gainers(current_results):
    global WIN_COUNT, LOSS_COUNT, PREVIOUS_TOP_GAINERS

    print("\n이전 상위 코인 평가 중...")
    if not PREVIOUS_TOP_GAINERS:
        print("평가할 이전 상위 코인이 없습니다.")
        return

    for previous in PREVIOUS_TOP_GAINERS:
        market = previous['market']
        previous_current_price = previous['current_price']
        current_price = current_results.get(market, {}).get('current_price', None)

        if current_price is None:
            print(f"{market} 데이터가 없어 평가할 수 없습니다.")
            continue

        if current_price > previous_current_price:
            print(f"{market}: 승 (현재 가격: {current_price:.2f} > 이전 가격: {previous_current_price:.2f})")
            WIN_COUNT += 1
        else:
            print(f"{market}: 패 (현재 가격: {current_price:.2f} <= 이전 가격: {previous_current_price:.2f})")
            LOSS_COUNT += 1

    print(f"총 승: {WIN_COUNT}, 총 패: {LOSS_COUNT}\n")

def run_all_markets_prediction():
    global PREVIOUS_TOP_GAINERS

    while True:
        results = fetch_and_predict_for_all()

        change_list = []

        for market, data in results.items():
            forecast = data["forecast"]
            df = data["df"]

            # 현재 가격 (마지막 캔들 데이터)
            current_price = data['current_price']

            # 6시간 뒤의 미래 가격 가져오기 (72번째 예측 값)
            predicted_price = forecast['yhat'].iloc[-1]

            # 상승률 계산
            price_change_percent = ((predicted_price - current_price) / current_price) * 100

            change_list.append({
                "market": market,
                "current_price": current_price,
                "predicted_price": predicted_price,
                "price_change_percent": price_change_percent,
                "forecast": forecast,
                "df": df
            })

            print(f"시장: {market}")
            print(f"현재 가격: {current_price:.2f}")
            print(f"6시간 뒤 예측 가격: {predicted_price:.2f}")
            print(f"가격 변동률: {price_change_percent:.2f}%")

        # 상위 5개 상승 코인 출력
        top_gainers = sorted(change_list, key=lambda x: x["price_change_percent"], reverse=True)[:5]

        print("\n상위 5개 상승 코인:")
        for i, gain in enumerate(top_gainers, 1):
            print(f"{i}. 시장: {gain['market']}, 가격 변동률: {gain['price_change_percent']:.2f}%")

        # 이전 Top Gainers 평가
        evaluate_top_gainers(results)

        
        # 현재 Top Gainers 저장
        PREVIOUS_TOP_GAINERS = top_gainers

        print("6시간 후 다시 실행됩니다...")
        
        asyncio.run(main_집계())
        
        time.sleep(21600)  # 6시간 대기

# 실행
if __name__ == "__main__":
    run_all_markets_prediction()
