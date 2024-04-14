import time
import ccxt
import telegram ## pip install python-telegram-bot
import asyncio
import datetime
import os

# 계좌 조회
api_key = ''
api_secret = ''

exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': True,
        'recvWindow': 10000
    }
})

symbol = 'BLZ/USDT'
stablecoin = 'USDT'

token = ''
chat_id = ''
timesleep = 0

count_추세_롱_보유갯수 = 0
count_추세_숏_보유갯수 = 0

익절갭 = 100
구매갯수 = 100

# 텔레그램 매크로 생성
async def main_시작():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"거래코인 = {symbol}\n스테이블 코인 = {stablecoin}\n기준갭 = {익절갭}\n코인 구매 단가 = {구매갯수}개\n자동 매매를 시작합니다")
            break        
        except:
            await asyncio.sleep(timesleep)
            continue

async def main_에러():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, '에러 발생')
            break        
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_롱청산_숏스위칭():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"롱 포지션 전량 매도\n익절물량 = {익절물량}\n누적익절물량 = {익절물량_누적}\n숏 포지션 진입\n청산 및 진입가격 = {last_trading_price}")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_숏청산_롱스위칭():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"숏 포지션 전량 매도\n익절물량 = {익절물량}\n누적익절물량 = {익절물량_누적}\n롱 포지션 진입\n청산 및 진입가격 = {last_trading_price}")
            break
        except:
            await asyncio.sleep(timesleep)
            continue


asyncio.run(main_시작())
while True:
    try:
        # 초기설정 (최소거래수량 확인 필요)
        balance = exchange.fetch_balance({'type':'future'})             # 선물 계좌로 변경                       
        symbol_price = exchange.fetch_ticker(symbol)['last']               # 코인 현재가 조회
        last_trading_price = symbol_price

        params = {
            'positionSide': 'LONG'
        }
        exchange.create_market_buy_order(symbol, 구매갯수, params)
        
        count_추세_롱_보유갯수 += 1
        asyncio.run(main_롱_매수_추적기_정산매매())
        break
    
    except:
        print("에러 발생")
        asyncio.run(main_에러())
        continue


while True : 
    try:
        # 초기 변수 리셋
        탈출_트리거 = 0
        익절물량 = 0
        count_누적 = 0
        # 본 매매 시작
        if count_추세_롱_보유갯수 > count_추세_숏_보유갯수 :
            
            while True:
                try:
                    symbol_price = exchange.fetch_ticker(symbol)['last']
                    
                    if 탈출_트리거 >= 1:
                        break
                    
                    if symbol_price > last_trading_price + 익절갭:
                        while True:
                            try:
                                last_trading_price = last_trading_price + 익절갭
                                count_누적 += 1
                                break
                            except:
                                asyncio.run(main_에러())
                                continue
                        
                    if symbol_price < last_trading_price - 익절갭:
                        while True:
                            try:
                                params = {
                                                'positionSide': 'LONG'
                                                }
                                exchange.create_market_sell_order(symbol, 구매갯수, params)
                                
                                params = {
                                                'positionSide': 'SHORT'
                                                }
                                exchange.create_market_sell_order(symbol, 구매갯수, params)
                                last_trading_price = last_trading_price - 익절갭
                                count_추세_롱_보유갯수 = 0
                                count_추세_숏_보유갯수 += 1
                                탈출_트리거 = 1
                                익절물량 = count_누적 - 1
                                익절물량_누적 += 익절물량
                                
                                asyncio.run(main_롱청산_숏스위칭())
                                break
                            except:
                                asyncio.run(main_에러())
                                continue
                except:
                    asyncio.run(main_에러())
                    continue
                
        if count_추세_롱_보유갯수 < count_추세_숏_보유갯수 :
            
            while True:
                try:
                    symbol_price = exchange.fetch_ticker(symbol)['last']
                    
                    if 탈출_트리거 >= 1:
                        break
                    
                    if symbol_price < last_trading_price - 익절갭:
                        while True:
                            try:
                                last_trading_price = last_trading_price - 익절갭
                                count_누적 += 1
                                break
                            except:
                                asyncio.run(main_에러())
                                continue
                    if symbol_price > last_trading_price + 익절갭:
                        while True:
                            try:
                                params = {
                                                'positionSide': 'SHORT'
                                                }
                                exchange.create_market_buy_order(symbol, 구매갯수, params)
                                
                                params = {
                                                'positionSide': 'LONG'
                                                }
                                exchange.create_market_buy_order(symbol, 구매갯수, params)
                                last_trading_price = last_trading_price + 익절갭
                                count_추세_롱_보유갯수 += 1
                                count_추세_숏_보유갯수 = 0
                                탈출_트리거 = 1
                                익절물량 = count_누적 - 1
                                익절물량_누적 += 익절물량
                                
                                asyncio.run(main_숏청산_롱스위칭())
                                break
                            except:
                                asyncio.run(main_에러())
                                continue
                except:
                    asyncio.run(main_에러())
                    continue
                
    except:
        asyncio.run(main_에러())
        continue
