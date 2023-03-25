import time
import ccxt
import telegram
import asyncio


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

# 카운팅
count1_0 = 0
count1_1 = 0
count1_2 = 0
count1_3 = 0
count1_4 = 0
count1_5 = 0
count1_6 = 0

count2_1 = 0

error1 = 0
error2 = 0

# 설정값
target_point = 0.03    # 손절 지점
switching_point = 0.0015   # 스위칭 지점
switching_ratio = 2      # 스위칭 배율
switching_count = 10     # 스위칭 횟수
leverage = 10            # 레버리지
symbol = 'XRP/BUSD'      # 거래 코인
start = 0.2
token = ""
chat_id = ''


async def main_시작(): #실행시킬 함수명 임의지정 
    bot = telegram.Bot(token)
    await bot.send_message(chat_id, f"target_point = {target_point}\nswitching_point = {switching_point}\nswitching_ratio = {switching_ratio}\nswitching_count = {switching_count}\nleverage = {leverage}\nsymbol = {symbol}\n자동 매매를 시작합니다")


asyncio.run(main_시작()) #봇 실행하는 코드


while True:

    try:
        # 초기설정 (최소거래수량 확인 필요)
        balance = exchange.fetch_balance({'type':'future'})             # 선물 계좌로 변경
        USDT_balance = balance['BUSD']['free']                          # 계좌 잔고 조회
        XRP_price = exchange.fetch_ticker(symbol)['last']               # 리플 현재가 조회
        short_amount = (USDT_balance * start * leverage) / XRP_price    # 초기 숏 물량(거래코인 최소거래수량 이상)
        long_amount = 0                                                # 초기 롱 물량
        count = 0                                                       # 카운팅
        reference_price = XRP_price                                     # 기준값 설정
        exchange.create_market_sell_order(symbol, short_amount)           # 초기 숏 물량 매수

    
        async def main_숏진입():

            bot = telegram.Bot(token)
            message = "숏 진입\nmargin : {} BUSD"
            await bot.send_message(chat_id, message.format(short_amount))

        asyncio.run(main_숏진입())



    except:
        error1 += 1
        print("에러1")

        async def main_에러1(): #실행시킬 함수명 임의지정
            
            bot = telegram.Bot(token)
            await bot.send_message(chat_id,'에러1')

        asyncio.run(main_에러1()) #봇 실행하는 코드

        continue
    

    while True:
        try:
            # USDT 잔고 및 비트코인 현재가 확인
            balance = exchange.fetch_balance({'type':'future'})
            USDT_balance = balance['BUSD']['free']
            XRP_price = exchange.fetch_ticker(symbol)['last']

            # 롱 포지션 물량이 없고 비트코인의 현재가가 기준값의 -1%일 경우 롱 포지션 생성(숏 포지션 3배 물량)
            if long_amount == 0 and XRP_price <= reference_price * (1 - switching_point) and count < switching_count:
                long_amount = short_amount * switching_ratio
                exchange.create_market_buy_order(symbol, long_amount)
                long_amount = long_amount - short_amount
                short_amount = 0
                count += 1
                print("롱 스위칭")

                async def main_롱스위칭(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "롱 스위칭\n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(USDT_balance))

                asyncio.run(main_롱스위칭()) #봇 실행하는 코드

            # 숏 포지션 물량이 없고 비트코인의 현재가가 기준값과 동일할 경우 숏 포지션 생성(롱 포지션 3배 물량)
            elif short_amount == 0 and XRP_price >= reference_price and count < switching_count:
                short_amount = long_amount * switching_ratio
                exchange.create_market_sell_order(symbol, short_amount)
                short_amount = short_amount - long_amount
                long_amount = 0
                count += 1
                print("숏 스위칭")

                async def main_숏스위칭(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "숏 스위칭\n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(USDT_balance))

                asyncio.run(main_숏스위칭()) #봇 실행하는 코드

            # 롱 포지션만 존재할 경우 목표가 지점에서 모든 포지션 정리
            elif short_amount == 0 and long_amount > 0 and XRP_price <= reference_price * (1 - (switching_point + target_point)):
                exchange.create_market_sell_order(symbol, long_amount)
                print("%d번 스위칭 후 손절"%(count))

                async def main_n번스위칭후손절(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "{}번 스위칭 후 손절\n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(count, USDT_balance))
                asyncio.run(main_n번스위칭후손절()) #봇 실행하는 코드

                async def main_손절후대기(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    await bot.send_message(chat_id,'2시간 대기 후 재진입 예정')
                asyncio.run(main_손절후대기()) #봇 실행하는 코드

                time.sleep(7200)

                if count == 1:
                    count1_1 += 1

                elif count == 2:
                    count1_2 += 1

                elif count == 3:
                    count1_3 += 1

                elif count == 4:
                    count1_4 += 1

                elif count == 5:
                    count1_5 += 1

                elif count == 6:
                    count1_6 += 1

                elif count == 0:
                    count1_0 += 1

                break

            # 숏 포지션만 존재할 경우 목표가 지점에서 모든 포지션 정리
            elif long_amount == 0 and short_amount > 0 and XRP_price >= reference_price * (1 + target_point): 
                exchange.create_market_buy_order(symbol, short_amount)
                print("%d번 스위칭 후 손절"%(count))

                async def main_n번스위칭후손절2(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "{}번 스위칭 후 손절\n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(count, USDT_balance))
                asyncio.run(main_n번스위칭후손절2()) #봇 실행하는 코드

                async def main_손절후대기2(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    await bot.send_message(chat_id,'2시간 대기 후 재진입 예정')
                asyncio.run(main_손절후대기2()) #봇 실행하는 코드

                time.sleep(7200)

                if count == 1:
                    count1_1 += 1

                elif count == 2:
                    count1_2 += 1

                elif count == 3:
                    count1_3 += 1

                elif count == 4:
                    count1_4 += 1

                elif count == 5:
                    count1_5 += 1

                elif count == 6:
                    count1_6 += 1

                elif count == 0:
                    count1_0 += 1

                break
                
            # 롱 보유중 - 마지막 스위칭 후 기준값 지점에서 모든 포지션 정리
            elif short_amount == 0 and XRP_price >= reference_price and count >= switching_count:
                exchange.create_market_sell_order(symbol, long_amount)
                print("%d번 스위칭 후 익절"%(count))

                async def main_n번스위칭후익절(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "{}번 스위칭 후 익절/n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(count, USDT_balance))

                asyncio.run(main_n번스위칭후익절()) #봇 실행하는 코드

                count2_1 += 1
                break

            # 숏 보유중 - 마지막 스위칭 후 스위칭 지점에서 모든 포지션 정리
            elif long_amount == 0 and XRP_price <= reference_price * (1 - switching_point) and count >= switching_count:
                exchange.create_market_buy_order(symbol, short_amount)
                print("%d번 스위칭 후 익절"%(count))

                async def main_n번스위칭후익절2(): #실행시킬 함수명 임의지정
                    bot = telegram.Bot(token)
                    message = "{}번 스위칭 후 익절\n현재 시드 : {} BUSD"
                    await bot.send_message(chat_id, message.format(count, USDT_balance))

                asyncio.run(main_n번스위칭후익절2()) #봇 실행하는 코드

                count2_1 += 1
                break

        except:
            error2 += 1
            print("에러2")

            async def main_에러2(): #실행시킬 함수명 임의지정
                bot = telegram.Bot(token)
                await bot.send_message(chat_id,'에러2')

            asyncio.run(main_에러2()) #봇 실행하는 코드

            continue

        time.sleep(1)


    print("----------------------")
    print("0번 스위칭 후 손절 %d회"%(count1_0))
    print("1번 스위칭 후 손절 %d회"%(count1_1))
    print("2번 스위칭 후 손절 %d회"%(count1_2))
    print("3번 스위칭 후 손절 %d회"%(count1_3))
    print("4번 스위칭 후 손절 %d회"%(count1_4))
    print("5번 스위칭 후 손절 %d회"%(count1_5))
    print("6번 스위칭 후 손절 %d회"%(count1_6))
    print("----------------------")
    print("%d번 익절"%(count2_1))
    print("----------------------")

    time.sleep(1)
