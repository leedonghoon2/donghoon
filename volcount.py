import time
import requests
from tqdm import tqdm
from datetime import datetime, timedelta
import ccxt
import asyncio
import aiohttp

async def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {"chat_id": chat_id, "text": message}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"텔레그램 메시지 전송 실패: {response.status}")

def get_binance_futures_symbols():
    try:
        # 바이낸스 선물 API 호출
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # 모든 선물 심볼 추출
        futures_symbols = {symbol['baseAsset'] for symbol in data['symbols']}
        print(f"바이낸스 선물 심볼 가져오기 완료: {len(futures_symbols)}개 심볼 발견.")
        return futures_symbols

    except Exception as e:
        print(f"오류 발생: {e}")
        return set()

def get_upbit_krw_symbols():
    try:
        # 업비트 API에서 마켓 목록 가져오기
        url = "https://api.upbit.com/v1/market/all"
        response = requests.get(url)
        response.raise_for_status()
        markets = response.json()

        # 원화 시장 심볼 필터링
        krw_symbols = {market['market'].split('-')[1] for market in markets if market['market'].startswith('KRW-')}
        print(f"업비트 KRW 심볼 가져오기 완료: {len(krw_symbols)}개 심볼 발견.")
        return krw_symbols

    except Exception as e:
        print(f"오류 발생: {e}")
        return set()

def get_upbit_candles(symbol, count=15):
    try:
        # 업비트 API에서 1시간봉 데이터 가져오기
        url = f"https://api.upbit.com/v1/candles/minutes/60?market=KRW-{symbol}&count={count}"
        response = requests.get(url)
        response.raise_for_status()
        candles = response.json()

        # 거래량 및 변동률 데이터 추출
        volumes = [candle['candle_acc_trade_volume'] for candle in candles]
        price_changes = [(candle['trade_price'] - candle['opening_price']) / candle['opening_price'] * 100 for candle in candles]
        print(f"{symbol} 캔들 데이터 가져오기 완료: {len(candles)}개 레코드 발견.")
        return volumes, price_changes

    except Exception as e:
        print(f"오류 발생: {e}")
        return [], []

def open_short_position(exchange, symbol, margin_usd, open_positions):
    try:
        # 코인 시장 정보 가져오기
        exchange.load_markets()  # 바이낸스 시장 데이터 로드
        market = exchange.market(symbol)

        # 마진을 기준으로 포지션 크기 계산
        price = exchange.fetch_ticker(symbol)['last']  # 현재 시장 가격
        amount = margin_usd / price  # USD 마진을 바탕으로 수량 계산

        # 숏 포지션 열기 (시장가 매도)
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='sell',
            amount=amount
        )

        # 포지션 목록에 추가
        open_positions.append({
            'symbol': symbol,
            'opened_at': datetime.now(),
            'order': order,
            'margin': margin_usd,
            'alert_count': 0  # 알림 횟수 초기화
        })

        print(f"{symbol} 숏 포지션 열기 성공: {order}")
        return order
    except Exception as e:
        print(f"{symbol} 포지션 열기 오류: {e}")
        return None

def close_position(exchange, position):
    try:
        symbol = position['symbol']
        amount = position['order']['amount']

        # 포지션 청산 (시장가 매수)
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=amount
        )

        print(f"{symbol} 포지션 청산 성공: {order}")
        return order
    except Exception as e:
        print(f"{symbol} 포지션 청산 오류: {e}")
        return None

async def main():
    # Telegram 설정
    telegram_token = ""
    chat_id = ""

    # 바이낸스 API 키와 시크릿 키 설정
    api_key = ''
    api_secret = ''

    # 진입 금액 설정 (USD)
    entry_amount_usd = 10  # 원하는 금액으로 설정

    # CCXT를 사용하여 바이낸스 선물 계좌 설정
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'defaultType': 'future',  # 선물 시장을 사용
        },
    })

    exchange.load_markets()  # 바이낸스 시장 데이터 로드

    binance_symbols = get_binance_futures_symbols()
    upbit_symbols = get_upbit_krw_symbols()

    # 교집합 계산
    common_symbols = binance_symbols & upbit_symbols
    print(f"교집합 심볼 발견: {len(common_symbols)}개 심볼.")

    # 열린 포지션 관리 리스트
    open_positions = []

    while True:
        print("새로운 사이클 시작.")
        start_time = datetime.now()
        next_run_time = (start_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        surged_symbols = []

        for symbol in tqdm(sorted(common_symbols), desc="심볼 처리 중"):
            volumes, price_changes = get_upbit_candles(symbol)
            if len(volumes) > 10 and len(price_changes) > 1:
                recent_volume = volumes[0]  # 가장 최근 거래량
                average_volume = sum(volumes[1:11]) / 10  # 직전 10개 거래량의 평균
                recent_change = price_changes[0]  # 가장 최근 변동률
                if recent_volume >= 7 * average_volume and recent_change > 0:
                    surged_symbols.append(symbol)
            await asyncio.sleep(0.2)  # 요청 간 딜레이 추가

        print(f"거래량 급등 코인: {surged_symbols}")
        await send_telegram_message(telegram_token, chat_id, f"거래량 급등 및 변동률 양수인 코인: {surged_symbols}")

        # 숏 포지션 열기
        for symbol in surged_symbols:
            binance_symbol = f"{symbol}USDT"
            order = open_short_position(exchange, binance_symbol, entry_amount_usd, open_positions)
            if order:
                print(f"{binance_symbol} 포지션 열림.")
                await send_telegram_message(telegram_token, chat_id, f"{binance_symbol} 숏 포지션 열림: {order}")

        # 열린 포지션 청산
        for position in open_positions[:]:
            position['alert_count'] += 1
            if position['alert_count'] == 3:  # 3번 알림 후 청산
                order = close_position(exchange, position)
                if order:
                    print(f"{position['symbol']} 포지션 청산됨.")
                    await send_telegram_message(telegram_token, chat_id, f"{position['symbol']} 포지션 청산됨: {order}")
                open_positions.remove(position)
            else:
                print(f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.")
                await send_telegram_message(telegram_token, chat_id, f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.")

        now = datetime.now()
        wait_time = (next_run_time - now).total_seconds()
        if wait_time > 0:
            print(f"다음 사이클까지 {wait_time:.2f}초 대기 중.")
            await send_telegram_message(telegram_token, chat_id, f"다음 사이클까지 {wait_time:.2f}초 대기 중.")
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    asyncio.run(main())
