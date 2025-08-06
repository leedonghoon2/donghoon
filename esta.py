from playwright.sync_api import sync_playwright
import time
import os

# ===== 설정 =====
HEADLESS_MODE = True
PROXY_SERVER = None  # 예: "123.123.123.123:8080" / 없으면 None

# ===== 로그인 정보 =====
LOGIN_ID = "ehdgnss1346"
LOGIN_PW = "dnflrkwhr12@"

# ===== 사전 설정 =====
DEPARTURE_BUTTON_NAME = "서울(모든 공항)"
DEPARTURE_CODE = "CJU"
ARRIVAL_BUTTON_NAME = "도착지"
ARRIVAL_CODE = "GMP"
TARGET_YEAR = 2025
TARGET_MONTH = 12
TARGET_DAY = "18"
START_TIME = "09:00"
END_TIME = "15:00"

# ===== 이메일 전송 설정 =====
SMTP_SERVER = "smtp.naver.com"
SMTP_PORT = 587
EMAIL_SENDER = "ehdgnss1346@naver.com"
EMAIL_PASSWORD = "dnflrkwhr1234~"
EMAIL_RECEIVER = "ehdgnss1346@naver.com"

# ===== 이메일 전송 함수 =====
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

def send_email_with_image(image_path):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "결제창 캡처 이미지"

    with open(image_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(image_path)}")
        msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
    print(f"📧 이메일 전송 완료 → {EMAIL_RECEIVER}")

# ===== 시간 비교 함수 =====
def time_in_range(t_str, start_str, end_str):
    t_h, t_m = map(int, t_str.split(":"))
    s_h, s_m = map(int, start_str.split(":"))
    e_h, e_m = map(int, end_str.split(":"))
    t_val = t_h * 60 + t_m
    s_val = s_h * 60 + s_m
    e_val = e_h * 60 + e_m
    return s_val <= t_val <= e_val

# ===== Cloudflare Challenge 감지 및 대기 =====
def wait_for_cloudflare(page, max_wait=15):
    print("🔍 Cloudflare Challenge 감지 여부 확인 중...")
    for i in range(max_wait):
        html = page.content()
        if ("잠시만 기다리십시오" in html) or ("challenge-platform" in html):
            print(f"⏳ Challenge 감지됨 → {i+1}초 대기 중...")
            time.sleep(1)
        else:
            print("✅ Challenge 통과!")
            return True
    print("⚠️ Challenge 통과 실패 또는 제한 시간 초과")
    return False

# ===== 메인 실행 =====
with sync_playwright() as p:
    launch_args = [
        "--start-maximized",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"
    ]
    browser_options = {"headless": HEADLESS_MODE, "args": launch_args}
    if PROXY_SERVER:
        browser_options["proxy"] = {"server": f"http://{PROXY_SERVER}"}

    browser = p.chromium.launch(**browser_options)
    context = browser.new_context(
        locale="ko-KR",
        viewport=None,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko'] });
    """)

    page = context.new_page()

    # 0️⃣ 로그인
    page.goto("https://www.eastarjet.com/newstar/PGWHB00001", timeout=60000)
    wait_for_cloudflare(page)
    page.fill("#PNWHB00001_userId", LOGIN_ID)
    page.fill("#PNWHB00001_userPw", LOGIN_PW)
    page.locator("#PNWHB00001_logonForm a:has-text('로그인')").click()
    time.sleep(1)

    # 1️⃣ 검색 페이지
    page.goto("https://main.eastarjet.com/search", timeout=60000)
    wait_for_cloudflare(page)
    page.locator("button:has-text('편도')").wait_for(state="visible")
    page.locator("button:has-text('편도')").click()

    # 2️⃣ 출발지 선택
    page.locator(f"button:has-text('{DEPARTURE_BUTTON_NAME}')").click()
    page.wait_for_selector('div[role="dialog"][data-state="open"] button', state="visible")
    dep_popup = page.locator('div[role="dialog"][data-state="open"]')
    dep_popup.locator(f"button:has-text('{DEPARTURE_CODE}')").click()

    # 3️⃣ 도착지 선택
    dep_popup = page.locator('div[role="dialog"][data-state="open"]')
    dep_popup.locator(f"button:has-text('{ARRIVAL_CODE}')").click()

    # 📅 달력 이동
    page.locator(".rdp-caption_label").first.wait_for(state="visible")
    while True:
        captions = [c.strip() for c in page.locator(".rdp-caption_label").all_inner_texts()]
        current_months = []
        for cap in captions:
            try:
                y, m = map(int, cap.split("."))
            except ValueError:
                parts = cap.replace("년", "").replace("월", "").split()
                y, m = map(int, parts)
            current_months.append((y, m))
        if any((y == TARGET_YEAR and m == TARGET_MONTH) for y, m in current_months):
            break
        if max(current_months) < (TARGET_YEAR, TARGET_MONTH):
            page.locator(".rdp-chevron").nth(1).click()
        else:
            page.locator(".rdp-chevron").nth(0).click()

    # 날짜 선택
    target_selector = f'[data-day="{TARGET_YEAR}-{TARGET_MONTH:02d}-{int(TARGET_DAY):02d}"] button'
    page.locator(target_selector).wait_for(state="visible")
    page.locator(target_selector).click()
    page.locator("button:has-text('선택')").click()

    # 4️⃣ 검색
    page.locator("button:has-text('검색')").wait_for(state="visible")
    page.locator("button:has-text('검색')").click()

    # 5️⃣ 최저가 선택
    page.locator("div.relative.my-2.flex").first.wait_for(state="visible")
    flight_cards = page.locator("div.relative.my-2.flex")
    count = flight_cards.count()
    min_price = None
    min_button = None
    for i in range(count):
        card = flight_cards.nth(i)
        dep_time = card.locator("div.relative.w-32").first.locator("div[class*='text-[22px]']").inner_text().strip()
        price_buttons = card.locator("button:has(span)").all()
        for btn in price_buttons:
            price_text = btn.locator("span").inner_text().strip().replace(",", "").replace("원", "")
            if price_text.isdigit():
                price = int(price_text)
                if time_in_range(dep_time, START_TIME, END_TIME):
                    if min_price is None or price < min_price:
                        min_price = price
                        min_button = btn
    if min_button:
        min_button.click()
        page.locator("button:has-text('탑승객 정보 입력')").wait_for(state="visible")
        page.locator("button:has-text('탑승객 정보 입력')").click()
    else:
        print("⚠️ 조건에 맞는 항공편이 없습니다.")
        browser.close()
        exit()

    # 8️⃣ 부가서비스 → 결제
    page.locator("text=부가서비스 선택").wait_for(state="visible")
    page.locator("text=부가서비스 선택").click()
    page.locator("text=바로 결제").wait_for(state="visible")
    page.locator("text=바로 결제").click()
    page.locator('button[role="checkbox"]').first.wait_for(state="visible")
    page.locator('button[role="checkbox"]').first.click()
    page.locator("button:has-text('아래로 스크롤')").click()
    page.locator("button:has-text('확인')").click()
    page.locator("button:has-text('아래로 스크롤')").click()
    page.locator("button:has-text('확인')").click()
    page.locator("button:has-text('결제하기')").click()
    page.locator('button[value="kakao"]').click()

    with context.expect_page() as popup_info:
        page.locator("button:has-text('결제하기')").click()

    time.sleep(1)
    payment_page = popup_info.value
    payment_page.wait_for_load_state("domcontentloaded")
    screenshot_path = os.path.join(os.getcwd(), "payment_page.png")
    payment_page.screenshot(path=screenshot_path, full_page=True)
    print(f"📸 결제창 캡처 완료: {screenshot_path}")

    # 이메일 전송
    send_email_with_image(screenshot_path)
    print("✅ 성공적으로 결제 단계까지 진행 및 이메일 발송 완료")
