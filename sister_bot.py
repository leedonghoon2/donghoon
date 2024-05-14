import time
import ccxt
import telegram ## pip install python-telegram-bot
import asyncio
import datetime
import os
import requests
from bs4 import BeautifulSoup
import re

api_key = ''
api_secret = ''

token = ''
chat_id = ''

시작_코인_갯수 = 1
업비트_코인_구매가격 = 700

symbol_delivery = 'XRP'
symbol_upbit = 'XRP/KRW'
symbol_spot = 'XRP/USDT'

#------------------------------------------------------------------------------------------------------------------------------------------------------------
url = 'https://www.google.com/search?q=1+USD+to+KRW'

upbit = ccxt.upbit()

exchange_delivery = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'delivery',
        'adjustForTimeDifference': True,
        'recvWindow': 10000
    }
})

exchange_spot = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
        'recvWindow': 10000
    }
})

def get_exchange_rate():
    # 구글 검색 URL
    url = 'https://www.google.com/search?q=1+USD+to+KRW'

    # HTTP 요청 보내기
    response = requests.get(url)

    # 응답 확인
    if response.status_code == 200:
        # HTML 문서 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        # 환율 정보 추출
        exchange_rate_text = soup.find('div', class_='BNeawe iBp4i AP7Wnd').text
        # 숫자만 추출
        exchange_rate = re.sub(r'[^\d.]', '', exchange_rate_text)
        return exchange_rate
    else:
        return None
    
async def main_정산(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"환율($) : {환율}￦\n현재 김프 : {formatted_김프}%\n누적 수익 코인 갯수 : {누적수익갯수_반올림}{symbol_delivery}\n누적 수익금($) : {누적수익금_달러_반올림}$\n누적 수익금(￦) : {누적수익금_원화_반올림}￦\n누적 수익률 : {누적수익률}%\n김프를 고려한 수익률 : {김프적용시수익률_반올림}%")
            break
        except:
            await asyncio.sleep(timesleep)
            continue



#-------------------------------------------------------김프-------------------------------------------------------------------------------------------------
while True:
    try:
        환율 = get_exchange_rate()
        환율 = float(환율)
        print(환율)
        while True:
            try:
                upbit_symbol_price = upbit.fetch_ticker(symbol_upbit)['last']
                print(upbit_symbol_price)

                binance_symbol_price = exchange_spot.fetch_ticker(symbol_spot)['last']
                binance_symbol_price_KRW = binance_symbol_price * 환율
                print(binance_symbol_price_KRW)

                김프 = ((upbit_symbol_price - binance_symbol_price_KRW)/binance_symbol_price_KRW) * 100
                formatted_김프 = "{:.3f}".format(김프)
                print(formatted_김프)
                break
            except:
                continue
        #-------------------------------------------------------누적수익금-------------------------------------------------------------------------------------------------
        while True:
            try:
                binance_symbol_price = exchange_spot.fetch_ticker(symbol_spot)['last']

                balance_delivery = exchange_delivery.fetch_balance()
                print(balance_delivery[symbol_delivery]['total'])

                누적수익갯수 = (balance_delivery[symbol_delivery]['total'] - 시작_코인_갯수) # 리플 갯수
                누적수익갯수_반올림 = round(balance_delivery[symbol_delivery]['total'] - 시작_코인_갯수,3) # 갯수

                누적수익금_달러_반올림 = round(누적수익갯수 * binance_symbol_price,2) # 달러
                누적수익금_달러 = (누적수익갯수 * binance_symbol_price)

                누적수익금_원화_반올림 = round(누적수익금_달러 * 환율,3)  
                누적수익률 = round((누적수익갯수 / 시작_코인_갯수) * 100,2) # %
                print(누적수익갯수_반올림)
                print(누적수익금_달러_반올림)
                print(누적수익금_원화_반올림)
                print(누적수익률)
                break
            except:
                continue

        #---------------------------------------------------------김프 적용시 수익률--------------------------------------------------------------------------------
        while True:
            try:
                upbit_symbol_price = upbit.fetch_ticker(symbol_upbit)['last']

                binance_symbol_price = exchange_spot.fetch_ticker(symbol_spot)['last']
                binance_symbol_price_KRW = binance_symbol_price * 환율

                balance_delivery = exchange_delivery.fetch_balance()
                balance_delivery = balance_delivery[symbol_delivery]['total']

                김프적용시수익률 = (((upbit_symbol_price * balance_delivery) - (업비트_코인_구매가격 * 시작_코인_갯수)) / (시작_코인_갯수 * 업비트_코인_구매가격)) * 100
                김프적용시수익률_반올림 = round((((upbit_symbol_price * balance_delivery) - (업비트_코인_구매가격 * 시작_코인_갯수)) / (시작_코인_갯수 * 업비트_코인_구매가격)) * 100,3)
                print(김프적용시수익률)
                break
            except:
                continue
            
        asyncio.run(main_정산())
        time.sleep(28800)
    except:
        continue
