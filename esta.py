from playwright.sync_api import sync_playwright
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

HEADLESS_MODE = True  # True = UI 없이 실행

# ===== 이메일 설정 (네이버 SMTP) =====
SMTP_SERVER = "smtp.naver.com"
SMTP_PORT = 587
EMAIL_SENDER = "your_naver_id@naver.com"   # 보내는 사람 네이버 메일
EMAIL_PASSWORD = "your_password"           # 네이버 비밀번호
EMAIL_RECEIVER = "target_email@example.com"  # 받을 메일 주소

# ===== 이메일 전송 함수 =====
def send_email_with_image(image_path):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "결제창 캡처 이미지"

    # 첨부파일 추가
    with open(image_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(image_path)}"
        )
        msg.attach(part)

    # SMTP 연결 후 전송
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()  # TLS 보안 연결
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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS_MODE, args=["--start-maximized"])
    
    # Cloudflare 우회 세팅
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
    page.locator("#PNWHB00001_logonForm").get_by_role("link", name="로그인").click()
    time.sleep(1)  # 로그인 처리 대기

    # 1️⃣ 검색 페이지
    page.goto("https://main.eastarjet.com/search", timeout=60000)
    page.get_by_role("tab", name="편도").wait_for(state="visible")
    page.get_by_role("tab", name="편도").click()

    # 2️⃣ 출발지 선택
    page.get_by_role("button", name=DEPARTURE_BUTTON_NAME).click()
    page.wait_for_selector('div[role="dialog"][data-state="open"] button', state="visible")
    dep_popup = page.locator('div[role="dialog"][data-state="open"]')
    dep_popup.locator(f"button:has-text('{DEPARTURE_CODE}')").click()

    # 3️⃣ 도착지 선택 → 자동 달력 열림
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
    page.get_by_role("button", name="선택").click()

    # 4️⃣ 검색
    page.get_by_role("button", name="검색").wait_for(state="visible")
    page.get_by_role("button", name="검색").click()

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
        page.get_by_role("button", name="탑승객 정보 입력").wait_for(state="visible")
        page.get_by_role("button", name="탑승객 정보 입력").click()
    else:
        print("⚠️ 조건에 맞는 항공편이 없습니다.")
        browser.close()
        exit()

    # 8️⃣ 부가서비스 → 결제
    page.get_by_text("부가서비스 선택", exact=True).wait_for(state="visible")
    page.get_by_text("부가서비스 선택", exact=True).click()
    page.get_by_text("바로 결제", exact=True).wait_for(state="visible")
    page.get_by_text("바로 결제", exact=True).click()
    page.locator('button[role="checkbox"]').first.wait_for(state="visible")
    page.locator('button[role="checkbox"]').first.click()
    page.get_by_role("button", name="아래로 스크롤").wait_for(state="visible")
    page.get_by_role("button", name="아래로 스크롤").click()
    page.get_by_role("button", name="확인").wait_for(state="visible")
    page.get_by_role("button", name="확인").click()
    page.get_by_role("button", name="아래로 스크롤").wait_for(state="visible")
    page.get_by_role("button", name="아래로 스크롤").click()
    page.get_by_role("button", name="확인").wait_for(state="visible")
    page.get_by_role("button", name="확인").click()
    page.get_by_role("button", name="결제하기").wait_for(state="visible")
    page.get_by_role("button", name="결제하기").click()
    page.locator('button[value="kakao"]').wait_for(state="visible")
    page.locator('button[value="kakao"]').click()

    with context.expect_page() as popup_info:
        page.get_by_role("button", name="결제하기").click()
    
    time.sleep(1)
    payment_page = popup_info.value
    payment_page.wait_for_load_state("domcontentloaded")
    screenshot_path = os.path.join(os.getcwd(), "payment_page.png")
    payment_page.screenshot(path=screenshot_path, full_page=True)
    print(f"📸 결제창 캡처 완료: {screenshot_path}")

    # 캡처 이미지를 네이버 메일로 전송
    send_email_with_image(screenshot_path)

    print("✅ 성공적으로 결제 단계까지 진행 및 이메일 발송 완료")
