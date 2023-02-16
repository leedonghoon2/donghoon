import time
import pyupbit

access = 
secret = 
upbit = pyupbit.Upbit(access, secret)

# 매수 주문 함수
def buy_order(price):
    try:
        # 1만원어치 비트코인 매수 주문
        krw_balance = upbit.get_balance("KRW")
        if krw_balance < 10000:
            return False
        upbit.buy_limit_order("BTC-KRW", price, 0.0001)
        return True
    except:
        return False

# 매도 주문 함수
def sell_order():
    try:
        # 보유 중인 비트코인 전량 매도
        btc_balance = upbit.get_balance("BTC")
        upbit.sell_market_order("BTC-KRW", btc_balance)
        return True
    except:
        return False

while True:
    try:
        # 5분봉 차트에서 볼린저밴드 Lower 가격 조회
        df = pyupbit.get_ohlcv("KRW-BTC", interval="minute5", count=21)
        lower = df['close'].rolling(20).mean() - (df['close'].rolling(20).std() * 2)

        # 볼린저밴드 Lower 가격과 매수 주문 가격이 일치하도록 갱신
        price = lower[-2]
        while not buy_order(price):
            price = lower[-1]

        # 매수 주문 체결 대기
        time.sleep(300)

        # 체결된 가격으로 각각 1만원씩 지정가 매수 주문 실행
        buy_price_list = [price * 0.9985, price * 0.997, price * 0.9955, price * 0.994, price * 0.9925, price * 0.991]
        for buy_price in buy_price_list:
            buy_order(buy_price)

        while True:
            # 1분봉 차트에서 현재가 조회
            cur_price = pyupbit.get_current_price("KRW-BTC")

            # 잔고의 수익률이 -1%에 도달하거나 또는 볼린저 밴드 Middle 가격에 도달한 경우 전량 매도
            middle = df['close'].rolling(20).mean()
            btc_balance = upbit.get_balance("BTC")
            total_balance = upbit.get_balance()
            if btc_balance > 0 and (total_balance / (btc_balance * cur_price) - 1) * 100 <= -1:
                sell_order()
                break
            elif cur_price >= middle[-1]:
                sell_order()
                break
            else:
                time.sleep(5)

        # 매도 주문 체결 대기
        time.sleep(300)

    except:
        time.sleep(1)
