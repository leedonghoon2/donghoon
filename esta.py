from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import os
from PIL import Image
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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

HEADLESS_MODE = True

# ===== 이메일 설정 (네이버 SMTP) =====
SMTP_SERVER = "smtp.naver.com"
SMTP_PORT = 587
EMAIL_SENDER = "ehdgnss1346@naver.com"
EMAIL_PASSWORD = "dnflrkwhr1234~"
EMAIL_RECEIVER = "ehdgnss1346@naver.com"

# ===== 이메일 전송 함수 =====
def send_email_with_image(image_path):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "결제창 캡처 이미지"

    with open(image_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(image_path)}"
        )
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

# ===== 안전 대기 + 클릭 함수 =====
def safe_wait_click(page, locator_str, description, timeout=30000):
    try:
        locator = page.locator(locator_str)
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()
    except PlaywrightTimeoutError:
        html_path = os.path.join(os.getcwd(), "debug_dump.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"❌ [{description}] 요소를 {timeout/1000}초 내에 찾지 못했습니다.")
        print(f"💾 현재 페이지 HTML을 저장했습니다: {html_path}")
        raise

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=HEADLESS_MODE,
        args=[
            "--start-maximized",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ]
    )

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

    # 0️⃣ 로그인 페이지
    page.goto("https://www.eastarjet.com/newstar/PGWHB00001", timeout=60000)
    page.wait_for_selector("#PNWHB00001_userId", state="visible")
    page.fill("#PNWHB00001_userId", LOGIN_ID)
    page.fill("#PNWHB00001_userPw", LOGIN_PW)
    safe_wait_click(page, "#PNWHB00001_logonForm a:has-text('로그인')", "로그인 버튼")
    time.sleep(1)

    # 1️⃣ 검색 페이지
    page.goto("https://main.eastarjet.com/search", timeout=60000)
    safe_wait_click(page, "button:has-text('편도')", "편도 버튼")

    # 2️⃣ 출발지 선택
    safe_wait_click(page, f"button:has-text('{DEPARTURE_BUTTON_NAME}')", "출발지 버튼")
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
    safe_wait_click(page, target_selector, "날짜 버튼")
    safe_wait_click(page, "button:has-text('선택')", "선택 버튼")

    # 4️⃣ 검색
    safe_wait_click(page, "button:has-text('검색')", "검색 버튼")

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
        safe_wait_click(page, "button:has-text('탑승객 정보 입력')", "탑승객 정보 입력 버튼")
    else:
        print("⚠️ 조건에 맞는 항공편이 없습니다.")
        browser.close()
        exit()

    # 8️⃣ 부가서비스 → 결제
    safe_wait_click(page, "text=부가서비스 선택", "부가서비스 선택 버튼")
    safe_wait_click(page, "text=바로 결제", "바로 결제 버튼")
    page.locator('button[role="checkbox"]').first.wait_for(state="visible")
    page.locator('button[role="checkbox"]').first.click()
    safe_wait_click(page, "button:has-text('아래로 스크롤')", "아래로 스크롤 버튼")
    safe_wait_click(page, "button:has-text('확인')", "확인 버튼")
    safe_wait_click(page, "button:has-text('아래로 스크롤')", "아래로 스크롤 버튼")
    safe_wait_click(page, "button:has-text('확인')", "확인 버튼")
    safe_wait_click(page, "button:has-text('결제하기')", "결제하기 버튼")
    page.locator('button[value="kakao"]').wait_for(state="visible")
    page.locator('button[value="kakao"]').click()

    with context.expect_page() as popup_info:
        safe_wait_click(page, "button:has-text('결제하기')", "결제하기 버튼")

    time.sleep(1)
    payment_page = popup_info.value
    payment_page.wait_for_load_state("domcontentloaded")
    screenshot_path = os.path.join(os.getcwd(), "payment_page.png")
    payment_page.screenshot(path=screenshot_path, full_page=True)
    print(f"📸 결제창 캡처 완료: {screenshot_path}")

    send_email_with_image(screenshot_path)
    print("✅ 성공적으로 결제 단계까지 진행 및 이메일 발송 완료")
