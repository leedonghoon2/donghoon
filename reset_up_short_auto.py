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

symbol = 'XRP/USDC'
stablecoin = 'USDC'

token = ''
chat_id = ''
익절갭 = 0.0006
시작_구매갯수 = 15
구매갯수_변경_단위 = 10

timesleep = 0
short_order_price = 0
long_order_price = 0
구매갯수 = 0
구매갯수_익절용 = 0
count_익절 = 0
count_롱_보유갯수 = 0
count_숏_보유갯수 = 0
last_order_id = 0
롱_미체결_주문수 = 0
롱_청산_주문갯수 = 0
바이낸스_청산_주문갯수 = 0

#--------------------------------------------------------------------------------------------------------------------------------------------
async def main_시작():
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"거래코인 = {symbol}\n스테이블 코인 = {stablecoin}\n익절갭 = {익절갭}\n코인 구매 단가 = {시작_구매갯수}개")
            break        
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_시작_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "시작 과정에서 오류 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_지정가_주문_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "숏 지정가 주문 과정에서 오류 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_청산_주문_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "숏 청산 주문 과정에서 오류 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_지정가_주문_갱신_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "숏 지정가 주문 갱신 과정에서 오류 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_미체결_주문_확인_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "숏 미체결 주문 확인 과정에서 오류 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_초기화(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "초기화 후 다시 시작")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
async def main_초기화_에러(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, "초기화 과정에서 에러 발생...")
            break
        except:
            await asyncio.sleep(timesleep)
            continue

async def main_정산_매매(): #실행시킬 함수명 임의지정
    while True:
        try:
            bot = telegram.Bot(token)
            await bot.send_message(chat_id, f"익절 = {count_익절}\n롱 보유 갯수 = {count_롱_보유갯수}\n숏 보유 갯수 = {count_숏_보유갯수}")
            break
        except:
            await asyncio.sleep(timesleep)
            continue
        
# asyncio.run(main_xxx())
#--------------------------------------------------------------------------------------------------------------------------------------------

while True:
    try:
        # 초기설정 (최소거래수량 확인 필요)
        balance = exchange.fetch_balance({'type':'future'})             # 선물 계좌로 변경                       
        symbol_price = exchange.fetch_ticker(symbol)['last']               # 코인 현재가 조회
        reference_price = symbol_price
        
        asyncio.run(main_시작())
        break
    
    except:
        asyncio.run(main_시작_에러()) 
        continue

while True : 
    try:
        positions = exchange.fetch_positions(symbols=[symbol])
        total_position_quantity = sum(position['contracts'] for position in positions)
        
        미체결주문 = exchange.fetch_open_orders(symbol=symbol)
        for order in 미체결주문:
            if order['info']['positionSide'] == 'SHORT':
                short_order_price = order['price']
            elif order['info']['positionSide'] == 'LONG':
                long_order_price = order['price']
        
        if total_position_quantity == 0 and round(short_order_price - long_order_price,10) != 익절갭 :
            timesleep(2)
            
            미체결주문 = exchange.fetch_open_orders(symbol=symbol)
            for order in 미체결주문:
                if order['info']['positionSide'] == 'SHORT':
                    exchange.cancel_order(order['id'], symbol=symbol)
            
            if count_숏_보유갯수 > 0 :
                count_익절 += count_숏_보유갯수
            
            short_order_price = 0
            long_order_price = 0
            구매갯수 = 0
            구매갯수_익절용 = 0
            count_롱_보유갯수 = 0
            count_숏_보유갯수 = 0
            last_order_id = 0
            숏_미체결_주문수 = 0
            숏_청산_주문갯수 = 0
            바이낸스_청산_주문갯수 = 0
            reference_price = symbol_price
            asyncio.run(main_초기화())
        
        if count_숏_보유갯수 < 구매갯수_변경_단위 :
            구매갯수 = 시작_구매갯수
            구매갯수_익절용 = 시작_구매갯수
        else:
            구매갯수 = 시작_구매갯수 * (count_숏_보유갯수 // 구매갯수_변경_단위 + 1)
            구매갯수_익절용 = 시작_구매갯수 * (count_숏_보유갯수 // (구매갯수_변경_단위+1) + 1)
        while True :
            try:    
                숏_미체결_주문수 = 0
                미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                for order in 미체결주문:
                    if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell':
                        숏_미체결_주문수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell')
                        print("숏 미체결 주문수는 :", 숏_미체결_주문수)
                break
            except:
                asyncio.run(main_미체결_주문_확인_에러())
                continue
                
        # 지정가 주문
        if 숏_미체결_주문수 < 1 :
            while True :
                try:
                    params = {
                                'positionSide': 'SHORT'
                                }
                    exchange.create_limit_sell_order(symbol, 구매갯수, reference_price + 익절갭, params)
                    break
                except:
                    asyncio.run(main_지정가_주문_에러())
                    continue
            
            reference_price = reference_price + 익절갭
                
            while True :
                try:
                    
                    while True:
                        try:
                            숏_미체결_주문수 = 0
                            
                            미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                            for order in 미체결주문:
                                if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell':
                                    숏_미체결_주문수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'sell')
                            
                            #print("미체결 주문수는 :", 숏_미체결_주문수)
                            break
                        except:
                            asyncio.run(main_미체결_주문_확인_에러())
                            continue
                        
                    if 숏_미체결_주문수 == 0 :
                        while True:
                            try:
                                params = {
                                            'positionSide': 'SHORT'
                                            }
                                exchange.create_limit_buy_order(symbol, 구매갯수, reference_price - 익절갭, params)
                                break
                            except:
                                asyncio.run(main_청산_주문_에러())
                                continue
                        숏_청산_주문갯수 += 1
                        count_숏_보유갯수 += 1
                        break
                    
                    while True:
                        try:
                            바이낸스_청산_주문갯수 = 0 
                            
                            미체결주문 = exchange.fetch_open_orders(symbol=symbol)
                            for order in 미체결주문:
                                if order['info']['positionSide'] == 'SHORT' and order['side'] == 'buy':
                                    바이낸스_청산_주문갯수 = sum(1 for order in 미체결주문 if order['info']['positionSide'] == 'SHORT' and order['side'] == 'buy')
                                    
                            #print("바이낸스_청산_주문갯수는", 바이낸스_청산_주문갯수)
                            break
                        except:
                            asyncio.run(main_미체결_주문_확인_에러())
                            continue
                    
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
                                        asyncio.run(main_지정가_주문_갱신_에러())
                                        continue
                        
                        count_익절 += ( 구매갯수_익절용 / 시작_구매갯수 )
                        count_숏_보유갯수 -= 1
                        reference_price = reference_price - (2 * 익절갭)
                        asyncio.run(main_정산_매매())
                        break
                    
                except:
                    continue
                
    except:
        continue
    
