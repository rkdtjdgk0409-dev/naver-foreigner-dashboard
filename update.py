import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


PAGE_URL = (
    "https://stock.naver.com/market/stock/kr/trend/foreigner"
    "?marketType=kospi&periodType=segment-1day&tradeType=0"
)
OUTPUT = Path("data.json")
KST = ZoneInfo("Asia/Seoul")


def to_number(text):
    """쉼표와 한글 단위가 포함된 값을 숫자로 바꿉니다."""
    if text is None:
        return None

    value = str(text).strip().replace(",", "").replace(" ", "")
    value = value.replace("주", "").replace("원", "")

    multipliers = [
        ("조", 1_000_000_000_000),
        ("백만", 1_000_000),
        ("억", 100_000_000),
        ("만", 10_000),
        ("천", 1_000),
    ]

    for unit, multiplier in multipliers:
        if value.endswith(unit):
            number_part = value[: -len(unit)]
            number_part = re.sub(r"[^0-9.+-]", "", number_part)
            if not number_part:
                return None
            return float(number_part) * multiplier

    cleaned = re.sub(r"[^0-9.+-]", "", value)
    if cleaned in ("", "+", "-", ".", "+.", "-."):
        return None

    number = float(cleaned)
    return int(number) if number.is_integer() else number


def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,2400")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )

    chrome_driver = shutil.which("chromedriver")

    if chrome_driver:
        return webdriver.Chrome(
            service=Service(chrome_driver),
            options=options,
        )

    # GitHub 실행 환경에 ChromeDriver 경로가 따로 잡힌 경우
    # Selenium Manager가 자동으로 찾아서 실행합니다.
    return webdriver.Chrome(options=options)


def wait_for_tables(driver):
    """네이버의 자바스크립트 표가 화면에 나타날 때까지 기다립니다."""
    def loaded(browser):
        body_text = browser.find_element(By.TAG_NAME, "body").text
        rows = browser.find_elements(By.CSS_SELECTOR, "table tbody tr")
        return (
            "순매수 상위" in body_text
            and "순매도 상위" in body_text
            and len(rows) >= 2
        )

    WebDriverWait(driver, 45).until(loaded)
    time.sleep(3)


def find_heading(soup, title):
    candidates = soup.find_all(
        ["h1", "h2", "h3", "h4", "strong", "div", "span"]
    )

    for tag in candidates:
        text = " ".join(tag.get_text(" ", strip=True).split())
        if text == title:
            return tag

    return None


def stock_code_from_row(row):
    for link in row.find_all("a", href=True):
        href = link["href"]

        patterns = [
            r"/stock/(\d{6})",
            r"/domestic/stock/(\d{6})",
            r"[?&]code=(\d{6})",
        ]

        for pattern in patterns:
            match = re.search(pattern, href)
            if match:
                return match.group(1)

    return ""


def parse_table(soup, title):
    heading = find_heading(soup, title)

    if heading is None:
        raise RuntimeError(f"'{title}' 제목을 찾지 못했습니다.")

    table = heading.find_next("table")

    if table is None:
        raise RuntimeError(f"'{title}' 아래의 표를 찾지 못했습니다.")

    items = []

    for row in table.find_all("tr"):
        cells = row.find_all("td")

        if not cells:
            continue

        stock_link = None
        stock_cell_index = None

        for index, cell in enumerate(cells):
            links = cell.find_all("a", href=True)

            for link in links:
                href = link.get("href", "")
                if (
                    re.search(r"/(?:domestic/)?stock/\d{6}", href)
                    or re.search(r"[?&]code=\d{6}", href)
                ):
                    stock_link = link
                    stock_cell_index = index
                    break

            if stock_link:
                break

        # 링크 구조가 바뀐 경우 첫 번째 글자 셀을 종목명으로 사용합니다.
        if stock_link:
            name = " ".join(stock_link.get_text(" ", strip=True).split())
        else:
            name = ""
            for index, cell in enumerate(cells):
                text = " ".join(cell.get_text(" ", strip=True).split())
                if text and not re.fullmatch(r"[\d,.\-+% ]+", text):
                    name = text
                    stock_cell_index = index
                    break

        if not name or stock_cell_index is None:
            continue

        numeric_values = []

        for cell in cells[stock_cell_index + 1:]:
            value = to_number(cell.get_text(" ", strip=True))
            if value is not None:
                numeric_values.append(value)

        # 표의 열 순서: 수량 → 금액 → 총 거래량
        if len(numeric_values) < 2:
            continue

        quantity = abs(numeric_values[0])
        amount = abs(numeric_values[1])
        total_volume = (
            abs(numeric_values[2])
            if len(numeric_values) >= 3
            else None
        )

        items.append(
            {
                "name": name,
                "code": stock_code_from_row(row),
                "quantity": quantity,
                "amount": amount,
                "total_volume": total_volume,
            }
        )

        if len(items) == 10:
            break

    if not items:
        raise RuntimeError(f"'{title}' 표에서 종목을 읽지 못했습니다.")

    for rank, item in enumerate(items, start=1):
        item["rank"] = rank

    return items


def fetch_data():
    driver = build_driver()

    try:
        driver.get(PAGE_URL)
        wait_for_tables(driver)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        buy = parse_table(soup, "순매수 상위")
        sell = parse_table(soup, "순매도 상위")

        return {
            "updated_at": datetime.now(KST).strftime(
                "%Y-%m-%d %H:%M KST"
            ),
            "source": PAGE_URL,
            "market": "KOSPI",
            "period": "1일",
            "unit": "네이버 표 표시 단위",
            "buy": buy,
            "sell": sell,
        }

    finally:
        driver.quit()


def main():
    data = fetch_data()

    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("데이터 저장 완료:", data["updated_at"])
    print("순매수:", [item["name"] for item in data["buy"]])
    print("순매도:", [item["name"] for item in data["sell"]])


if __name__ == "__main__":
    main()
