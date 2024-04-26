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

symbol = '1000PEPE/USDC'
stablecoin = 'USDC'

token = ''
chat_id = ''
timesleep = 0

count_익절 = 0
count_롱_보유갯수 = 0
count_숏_보유갯수 = 0
last_order_id = 0
숏_미체결_주문수 = 0
숏_청산_주문갯수 = 0
바이낸스_청산_주문갯수 = 0

익절갭 = 0.00001
구매갯수 = 700
포지션최대보유가능갯수 = 150
스페어물량 = 0
청산물량 = 10

while True:
    try:
        # 초기설정 (최소거래수량 확인 필요)
        balance = exchange.fetch_balance({'type':'future'})             # 선물 계좌로 변경                       
        symbol_price = exchange.fetch_ticker(symbol)['last']               # 코인 현재가 조회
        reference_price = symbol_price
        
        break
    
    except:
        print("에러1")
        asyncio.run(main_에러1()) #봇 실행하는 코드
        continue

while True : 
    try:
        숏_미체결_주문수 = 0
        미체결주문 = exchange.fetch_open_orders(symbol=symbol)
        for order in 미체결주문:
            if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell':
                숏_미체결_주문수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell')
        print("숏 미체결 주문수는 :", 숏_미체결_주문수)
                
                        
        if 숏_미체결_주문수 < 1 :
            params = {
                        'positionSide': 'SHORT'
                        }
            exchange.create_limit_sell_order(symbol, 구매갯수, reference_price + 익절갭, params)
            reference_price = reference_price + 익절갭
            print("숏 지정가 주문 완료")
            while True :
                try:
                    time.sleep(0.1)
                    숏_미체결_주문수 = 0
                    바이낸스_청산_주문갯수 = 0
                    
                    미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                    for order in 미체결주문:
                        if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell':
                            숏_미체결_주문수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell')
                    
                    print("미체결 주문수는 :", 숏_미체결_주문수)
                    
                    if 숏_미체결_주문수 == 0 :
                        params = {
                                     'positionSide': 'SHORT'
                                    }
                        exchange.create_limit_buy_order(symbol, 구매갯수, reference_price - 익절갭, params)
                        숏_청산_주문갯수 += 1
                        break
                    
                    미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                    for order in 미체결주문:
                        if order['info']['positionSide'] == 'SHORT' and order['side'] == 'buy':
                            바이낸스_청산_주문갯수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'buy')
                            
                    print("바이낸스_청산_주문갯수는", 바이낸스_청산_주문갯수)
                    
                    if 숏_청산_주문갯수 > 바이낸스_청산_주문갯수 :
                        숏_청산_주문갯수 = 바이낸스_청산_주문갯수
                        
                        미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                        if 미체결주문:
                            # 가장 최근 주문 가져오기
                            short_order_found = False
                            for order in reversed(미체결주문):  # 최근 주문부터 확인
                                # 직전 거래가 'SHORT' 포지션인 경우에만 주문 취소
                                if order['info']['positionSide'] == 'SHORT':
                                    last_order_id = order['id']
                                    
                                    try:
                                        exchange.cancel_order(id=last_order_id, symbol=symbol)
                                        short_order_found = True
                                        break
                                    except:
                                        continue
                        
                        reference_price = reference_price - (2 * 익절갭)
                        break
                    
                except:
                    continue
                
    except:
        continue
