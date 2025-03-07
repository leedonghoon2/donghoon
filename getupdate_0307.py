import asyncio
import ccxt.async_support as ccxt  # 비동기 버전 사용
from datetime import datetime, timedelta
import aiohttp
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO

# 누적 수익 데이터를 기록할 리스트 (각 항목: (시간, 누적 수익 (USD)))
profit_history = []

# ---------------------------
# 텔레그램 관련 함수들
# ---------------------------

# 텔레그램 메시지 전송 함수
async def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {"chat_id": chat_id, "text": message}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"Telegram message failed: {response.status}")

# 텔레그램 사진(그래프) 전송 함수
async def send_telegram_photo(token, chat_id, photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", chat_id)
    data.add_field("caption", caption)
    data.add_field("photo", photo_bytes, filename="profit_graph.png", content_type="image/png")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.post(url, data=data) as response:
            if response.status != 200:
                print(f"Failed to send photo: {response.status}")

async def log_and_notify(message, telegram_token, chat_id):
    print(message)
    await send_telegram_message(telegram_token, chat_id, message)

# 누적 수익률 그래프 생성 및 전송 함수 (X축, Y축 범위 지정 포함)
async def send_profit_graph(telegram_token, chat_id):
    if not profit_history:
        await send_telegram_message(telegram_token, chat_id, "누적 수익 데이터가 없습니다.")
        return

    times, profits = zip(*profit_history)
    plt.figure(figsize=(12, 6))
    plt.style.use("seaborn-darkgrid")
    plt.plot(times, profits, marker='D', color='blue', linestyle='-', linewidth=2, markersize=6)
    plt.title("Dong's System Trading Result", fontsize=16)
    plt.xlabel("Time", fontsize=14)
    plt.ylabel("Total Profit (USD)", fontsize=14)
    x_min = times[0]
    x_max = datetime.now()
    plt.xlim(x_min, x_max)
    y_min = min(profits)
    y_max = max(profits)
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    plt.ylim(y_min, y_max)
    plt.gcf().autofmt_xdate()
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.grid(True)
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches="tight")
    buf.seek(0)
    plt.close()
    await send_telegram_photo(telegram_token, chat_id, buf.read(), caption="누적 수익률 그래프")

# 텔레그램 업데이트 폴링 함수  
# “수익률 확인” -> 누적 수익 그래프 전송  
# “진입금액 변경” -> “몇 달러로 변경하시겠습니까?” 응답 후, “XXX달러” 메시지로 진입금액 업데이트
async def poll_telegram_updates(telegram_token, chat_id, config):
    waiting_for_entry_change = False
    last_update_id = None
    while True:
        url = f"https://api.telegram.org/bot{telegram_token}/getUpdates"
        params = {}
        if last_update_id is not None:
            params["offset"] = last_update_id + 1
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ok"):
                            for update in data.get("result", []):
                                last_update_id = update["update_id"]
                                if "message" in update:
                                    text = update["message"].get("text", "").strip()
                                    # 누적 수익률 그래프 요청
                                    if text == "수익률 확인":
                                        await send_profit_graph(telegram_token, chat_id)
                                    # 진입금액 변경 명령 감지
                                    elif text == "진입금액 변경" and not waiting_for_entry_change:
                                        await send_telegram_message(telegram_token, chat_id, "몇 달러로 변경하시겠습니까?")
                                        waiting_for_entry_change = True
                                    # 사용자가 XXX달러 형식으로 응답한 경우
                                    elif waiting_for_entry_change and text.endswith("달러"):
                                        amount_str = text.replace("달러", "").strip()
                                        try:
                                            new_amount = float(amount_str)
                                            config["entry_amount_usd"] = new_amount
                                            await send_telegram_message(telegram_token, chat_id, f"{new_amount}달러로 진입금액이 변경되었습니다")
                                        except Exception as e:
                                            await send_telegram_message(telegram_token, chat_id, f"입력값 오류: {text}")
                                        waiting_for_entry_change = False
        except Exception as e:
            print("Error in poll_telegram_updates:", e)
        await asyncio.sleep(5)

# ---------------------------
# 거래 관련 함수들
# ---------------------------

def get_timeframe_timedelta(timeframe_str):
    try:
        num = int(timeframe_str[:-1])
    except ValueError:
        num = 1
    unit = timeframe_str[-1].lower()
    if unit == 'm':
        return timedelta(minutes=num)
    elif unit == 'h':
        return timedelta(hours=num)
    elif unit == 'd':
        return timedelta(days=num)
    else:
        return timedelta(minutes=1)

async def fetch_binance_candles(exchange, symbol, timeframe, limit=12, semaphore=None, telegram_token="", chat_id=""):
    while True:
        try:
            async with semaphore:
                candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return candles
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching candles: {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error fetching candles for {symbol}: {e}")
                return []

def analyze_candles(candles, num_candles):
    if len(candles) < num_candles + 2:
        return None, None, None, None, []
    target_candle = candles[-2]
    previous_candles = candles[-(num_candles + 2):-2]
    previous_volumes = [candle[5] for candle in previous_candles]
    average_volume = sum(previous_volumes) / len(previous_volumes)
    volume_threshold = 3 * average_volume
    target_volume = target_candle[5]
    opening_price = target_candle[1]
    closing_price = target_candle[4]
    target_change = (closing_price - opening_price) / opening_price * 100
    return target_volume, average_volume, volume_threshold, target_change, previous_volumes

async def process_symbol(symbol, exchange, num_candles, timeframe, semaphore, telegram_token, chat_id):
    candles = await fetch_binance_candles(
        exchange, symbol, timeframe, limit=num_candles + 2,
        semaphore=semaphore, telegram_token=telegram_token, chat_id=chat_id
    )
    if not candles:
        return None, None
    target_volume, average_volume, volume_threshold, target_change, previous_volumes = analyze_candles(candles, num_candles)
    message = (
        f"{symbol} 기준봉 정보:\n"
        f"- 시간: {datetime.fromtimestamp(candles[-2][0] / 1000).isoformat()}\n"
        f"- 거래량: {target_volume}\n"
        f"- 변동률: {target_change:.2f}%\n"
        f"- 이전 {num_candles}개봉 거래량 리스트: {previous_volumes}\n"
        f"- 이전 {num_candles}개봉 평균 거래량: {average_volume}\n"
        f"- 평균 거래량의 3배값: {volume_threshold}\n"
    )
    return message, target_volume >= volume_threshold and target_change > 0

# 수정된 open_short_position 함수:
# -2027 에러 발생 시, 해당 종목의 최대 허용 레버리지를 조회하여,
# 만약 그 값이 20배 미만이면 그 값으로 레버리지를 업데이트하고,
# 텔레그램 알림 전송 후 주문을 재시도합니다.
async def open_short_position(exchange, symbol, margin_usd, open_positions, semaphore, telegram_token, chat_id):
    while True:
        try:
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching ticker (open position): {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error opening position for {symbol}: {e}")
                return None
    price = ticker['last']
    amount = margin_usd / price
    try:
        async with semaphore:
            order = await exchange.create_order(symbol, type='market', side='sell', amount=amount)
    except Exception as e:
        err_str = str(e)
        # 에러 코드 -2027 감지 시 레버리지 수정 시도
        if '"code":-2027' in err_str:
            try:
                # ccxt의 Binance 선물 API 엔드포인트를 사용하여 레버리지 브래킷 조회
                brackets = await exchange.fapiPrivate_get_leverage_bracket({'symbol': symbol})
                new_leverage = None
                if brackets and len(brackets) > 0:
                    symbol_brackets = brackets[0].get('brackets', [])
                    if symbol_brackets and len(symbol_brackets) > 0:
                        new_leverage = symbol_brackets[0].get('initialLeverage')
                # 최대 허용 레버리지가 20 이상이거나 값을 가져오지 못하면 업데이트하지 않음.
                if new_leverage is None or new_leverage >= 20:
                    await log_and_notify(f"{symbol}의 최대 허용 레버리지가 20 이상이므로 레버리지 업데이트를 하지 않습니다.", telegram_token, chat_id)
                    return None
                # 레버리지 업데이트 전 텔레그램 알림 전송
                await log_and_notify(f"{symbol}의 최대 허용 레버리지를 초과하여 해당 종목의 레버리지를 {new_leverage}배로 수정합니다.", telegram_token, chat_id)
                # ccxt 엔드포인트를 사용하여 레버리지 업데이트 (POST /fapi/v1/leverage)
                await exchange.fapiPrivate_post_leverage({'symbol': symbol, 'leverage': new_leverage})
                await log_and_notify(f"{symbol}의 변경된 레버리지로 포지션 오픈을 재시도합니다.", telegram_token, chat_id)
                async with semaphore:
                    order = await exchange.create_order(symbol, type='market', side='sell', amount=amount)
                await log_and_notify(f"{symbol}의 포지션 재오픈을 성공했습니다", telegram_token, chat_id)
            except Exception as e2:
                await log_and_notify(f"Failed to update leverage for {symbol}: {e2}", telegram_token, chat_id)
                return None
        else:
            await log_and_notify(f"Failed to place short market order for {symbol}: {e}", telegram_token, chat_id)
            return None

    fee_open = margin_usd * 0.0004
    open_positions.append({
        'symbol': symbol,
        'opened_at': datetime.now(),
        'open_price': price,
        'margin': margin_usd,
        'amount': amount,
        'alert_count': 0,
        'order': order,
        'open_fee': fee_open
    })
    return order, fee_open

# 실제 포지션 청산 함수 (실제 시장가 주문 실행)
async def close_position(exchange, position, semaphore, telegram_token, chat_id):
    while True:
        try:
            symbol = position['symbol']
            async with semaphore:
                ticker = await exchange.fetch_ticker(symbol)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                await log_and_notify(
                    f"Binance rate limit reached for {symbol} while fetching ticker (close position): {e}. Retrying in 1 second...",
                    telegram_token,
                    chat_id
                )
                await asyncio.sleep(1)
            else:
                print(f"Error closing position for {symbol}: {e}")
                return None, 0, 0
    current_price = ticker['last']
    open_price = position['open_price']
    profit = (open_price - current_price) * position['amount']
    try:
        async with semaphore:
            order = await exchange.create_order(symbol, type='market', side='buy', amount=position['amount'])
    except Exception as e:
        await log_and_notify(f"Failed to place close market order for {symbol}: {e}", telegram_token, chat_id)
        return None, 0, 0
    fee_close = (current_price * position['amount']) * 0.0004
    return order, profit, fee_close

async def manage_open_positions(open_positions, exchange, telegram_token, chat_id, simulated_total_profit, total_seed, accumulated_fee, semaphore):
    for position in open_positions[:]:
        position['alert_count'] += 1
        await log_and_notify(
            f"{position['symbol']} 포지션 알림 {position['alert_count']}회 발송.",
            telegram_token,
            chat_id
        )
        if position['alert_count'] >= 4:
            try:
                order, profit, fee_close = await close_position(exchange, position, semaphore, telegram_token, chat_id)
                simulated_total_profit += profit
                accumulated_fee += fee_close
                open_positions.remove(position)
                profit_rate = (simulated_total_profit / total_seed) * 100
                await log_and_notify(
                    f"포지션 청산: {position['symbol']} / 수익: {profit:.2f} USD / 누적 수익: {simulated_total_profit:.2f} USD / "
                    f"누적 수익률: {profit_rate:.2f}% / 누적 수수료: {accumulated_fee:.4f} USD",
                    telegram_token,
                    chat_id
                )
            except Exception as e:
                await log_and_notify(
                    f"{position['symbol']} 포지션 청산 오류: {e}",
                    telegram_token,
                    chat_id
                )
    return simulated_total_profit, accumulated_fee

async def recheck_mismatched_symbols(mismatched_symbols, exchange, num_candles, timeframe, semaphore, telegram_token, chat_id):
    valid_symbols = []
    for symbol in mismatched_symbols[:]:
        candles = await fetch_binance_candles(
            exchange, symbol, timeframe, limit=num_candles+2,
            semaphore=semaphore, telegram_token=telegram_token, chat_id=chat_id
        )
        if candles:
            target_volume, average_volume, volume_threshold, target_change, _ = analyze_candles(candles, num_candles)
            if target_volume >= volume_threshold and target_change > 0:
                valid_symbols.append(symbol)
    return valid_symbols

# ---------------------------
# 메인 실행 함수
# ---------------------------
async def main():
    telegram_token = ""  # 텔레그램 봇 토큰
    chat_id = ""         # 텔레그램 채팅 ID
    
    api_key = ""
    api_secret = ""
    
    # entry_amount_usd를 딕셔너리로 관리하여 동적으로 업데이트 가능하도록 함
    config = {"entry_amount_usd": 100}
    num_candles = 7
    total_seed = 300
    
    candle_timeframe = '1h'
    simulated_total_profit = 0
    accumulated_fee = 0
    
    initial_start_str = "2023-12-31 14:00:00"  
    if initial_start_str:
        initial_start_time = datetime.strptime(initial_start_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if now < initial_start_time:
            wait_time = (initial_start_time - now).total_seconds()
            await log_and_notify(
                f"최초 실행 시각까지 {wait_time:.2f}초 대기합니다. (최초 실행 시각: {initial_start_time.strftime('%Y-%m-%d %H:%M:%S')})",
                telegram_token,
                chat_id
            )
            await asyncio.sleep(wait_time)
    now = datetime.now()
    cycle_start = now.replace(minute=0, second=0, microsecond=0)
    await log_and_notify(f"최초 사이클 시작 시각: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
    
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })
    await exchange.load_markets()
    
    binance_symbols = []
    for symbol in exchange.symbols:
        try:
            market = exchange.market(symbol)
            if symbol.endswith('USDT') and market['info']['contractType'] == 'PERPETUAL':
                standardized_symbol = symbol.split(':')[0]
                binance_symbols.append(standardized_symbol)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")
    binance_symbols = list(set(binance_symbols))
    
    open_positions = []
    mismatched_symbols = []
    
    semaphore = asyncio.Semaphore(10)
    
    # 텔레그램 업데이트 폴링 작업 시작 (config 객체를 전달하여 진입금액 변경 가능)
    telegram_poll_task = asyncio.create_task(poll_telegram_updates(telegram_token, chat_id, config))
    
    while True:
        await log_and_notify(f"사이클 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", telegram_token, chat_id)
        tasks = [
            process_symbol(symbol, exchange, num_candles, candle_timeframe, semaphore, telegram_token, chat_id)
            for symbol in binance_symbols
        ]
        results = await asyncio.gather(*tasks)
        
        trading_list = []
        for result in results:
            if result is None:
                continue
            message, is_trading_candidate = result
            if message:
                symbol_name = message.split(' ')[0]
                if is_trading_candidate:
                    trading_list.append(symbol_name)
                else:
                    mismatched_symbols.append(symbol_name)
        
        resolved_symbols = await recheck_mismatched_symbols(
            mismatched_symbols, exchange, num_candles, candle_timeframe, semaphore, telegram_token, chat_id
        )
        trading_list.extend(resolved_symbols)
        trading_list = list(dict.fromkeys(trading_list))
        
        await log_and_notify(f"Trading candidates: {trading_list}", telegram_token, chat_id)
        
        if len(trading_list) >= 15:
            await log_and_notify(
                f"매매 대상 코인이 {len(trading_list)}개 발생하여 이번 사이클은 신규 매수를 진행하지 않습니다.",
                telegram_token,
                chat_id
            )
        else:
            # config["entry_amount_usd"] 값을 사용하여 주문 진행
            for symbol in trading_list:
                result = await open_short_position(exchange, symbol, config["entry_amount_usd"], open_positions, semaphore, telegram_token, chat_id)
                if result:
                    order, fee_open = result
                    accumulated_fee += fee_open
                    await log_and_notify(
                        f"Short position opened for {symbol}: {order}. Open fee: {fee_open:.4f} USD / 누적 수수료: {accumulated_fee:.4f} USD",
                        telegram_token,
                        chat_id
                    )
        
        simulated_total_profit, accumulated_fee = await manage_open_positions(
            open_positions, exchange, telegram_token, chat_id,
            simulated_total_profit, total_seed, accumulated_fee, semaphore
        )
        
        profit_history.append((datetime.now(), simulated_total_profit))
        mismatched_symbols.clear()
        
        now = datetime.now()
        next_run_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        wait_time = (next_run_time - now).total_seconds()
        await log_and_notify(
            f"다음 사이클까지 {wait_time:.2f}초 대기합니다. (다음 실행 시각: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')})",
            telegram_token,
            chat_id
        )
        await asyncio.sleep(wait_time)
    
    # 필요시 exchange 연결 종료
    # await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
