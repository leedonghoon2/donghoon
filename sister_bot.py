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

token = '6277404128:AAGoL8YfdkfRLRrt8OeOxBuIPwFgwRuOkjI'
chat_id = '1002076075628'

시작_시드 = 10500000
시작_시드_tele = '10,500,000'

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
            await bot.send_message(chat_id, f"환율($) : {환율}￦\n현재 김프 : {formatted_김프}%\n현재 코인 갯수 : {현재코인갯수}{symbol_delivery}\n현재 바이낸스 시드($) : {현재_시드_반올림}$\n---------------------------------\n누적 수익금($) : {누적수익금_달러_반올림}$\n누적 수익금(￦) : {누적수익금_원화_반올림}￦\n누적 수익률 : {누적수익률}%\n(단, 처음에 코인 전송 시 발생한 손실분 포함)\n---------------------------------\n김프를 고려한 수익률 : {김프적용시수익률_반올림}%\n업비트로 전송 시 수익금 : {최종_수익금_반올림}￦\n---------------------------------\n수익률(김프고려) & 현재 김프 갭 : {김프고려수익률_김프_갭차이}%\n(위 %가 0이면 초기 김프만큼의 수익 발생)")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_시작(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"📢펀딩비 전략 수익률 알림봇을 실행합니다.\n시작 금액(￦) : {시작_시드_tele}￦")
            break
        except:
            await asyncio.sleep(timesleep)
            continue


asyncio.run(main_시작())
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

                # 누적수익갯수 = (balance_delivery[symbol_delivery]['total'] - 시작_코인_갯수) # 리플 갯수
                # 누적수익갯수_반올림 = round(balance_delivery[symbol_delivery]['total'] - 시작_코인_갯수,3) # 갯수

                 # 달러
                누적수익금_달러 = ((balance_delivery[symbol_delivery]['total'] * binance_symbol_price) - (시작_시드 / 환율))
                누적수익금_달러_반올림 = round(누적수익금_달러,2)
                print(누적수익금_달러_반올림)
                
                누적수익금_원화_반올림 = round(누적수익금_달러 * 환율,3)  
                print(누적수익금_원화_반올림)
                
                누적수익률 = round((누적수익금_원화_반올림/시작_시드)*100,2) # %
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

                김프적용시수익률 = (((upbit_symbol_price * balance_delivery) - (시작_시드)) / (시작_시드)) * 100
                김프적용시수익률_반올림 = round((((upbit_symbol_price * balance_delivery) - (시작_시드)) / (시작_시드)) * 100,3)
                print(김프적용시수익률)
                break
            except:
                continue
        
        while True:
            try:
                balance_delivery = exchange_delivery.fetch_balance()
                현재코인갯수 = round(balance_delivery[symbol_delivery]['total'],3)
                break
            except:
                continue
            
        while True:
            try:
                upbit_symbol_price = upbit.fetch_ticker(symbol_upbit)['last']
                
                balance_delivery = exchange_delivery.fetch_balance()
                최종_수익금 = balance_delivery[symbol_delivery]['total'] * upbit_symbol_price - 시작_시드
                최종_수익금_반올림 = round(최종_수익금,0)
                break
            except:
                continue
            
        while True:
            try:
                balance_delivery = exchange_delivery.fetch_balance()
                balance_delivery = balance_delivery[symbol_delivery]['total']
                
                binance_symbol_price = exchange_spot.fetch_ticker(symbol_spot)['last']
                
                현재_시드 = balance_delivery * binance_symbol_price
                현재_시드_반올림 = round(현재_시드,3)
                break
            except:
                continue
        
        김프고려수익률_김프_갭차이 = 김프적용시수익률_반올림 - round(김프,3)
        asyncio.run(main_정산())
        
        time.sleep(28800)
    except:
        continue
