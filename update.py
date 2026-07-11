import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


URL = "https://finance.naver.com/sise/sise_deal_rank.naver"
OUTPUT = Path("data.json")
KST = ZoneInfo("Asia/Seoul")


def number(text: str):
    """'1,234' 같은 글자를 숫자로 바꿉니다."""
    cleaned = re.sub(r"[^0-9.-]", "", text.replace(",", ""))
    if cleaned in ("", "-", ".", "-."):
        return None

    value = float(cleaned)
    return int(value) if value.is_integer() else value


def stock_code(link):
    """네이버 종목 링크에서 6자리 종목코드를 꺼냅니다."""
    href = link.get("href", "")
    match = re.search(r"code=(\d{6})", href)
    return match.group(1) if match else ""


def group_order(table):
    """
    표의 왼쪽과 오른쪽이 순매수인지 순매도인지 자동 확인합니다.
    반환 예: ["sell", "buy"]
    """
    order = []

    for row in table.find_all("tr")[:4]:
        for cell in row.find_all(["th", "td"]):
            text = cell.get_text(" ", strip=True)

            if "순매도상위" in text and "sell" not in order:
                order.append("sell")
            elif "순매수상위" in text and "buy" not in order:
                order.append("buy")

    if len(order) != 2:
        # 네이버 표의 일반적인 배치
        return ["sell", "buy"]

    return order


def parse_group(cells, start, end):
    """
    한쪽 영역에서 종목명, 수량, 금액을 읽습니다.
    네이버 표는 보통 '종목명 / 수량 / 금액' 순서입니다.
    """
    company_cell = None

    for index in range(start, end):
        if cells[index].select_one("a.company"):
            company_cell = index
            break

    if company_cell is None:
        return None

    link = cells[company_cell].select_one("a.company")
    name = link.get_text(" ", strip=True)

    values = []
    for index in range(company_cell + 1, end):
        value = number(cells[index].get_text(" ", strip=True))
        if value is not None:
            values.append(value)

    if not values:
        return None

    # 수량과 금액이 모두 있으면 마지막 값이 금액입니다.
    amount = abs(values[-1])
    quantity = abs(values[-2]) if len(values) >= 2 else None

    return {
        "name": name,
        "code": stock_code(link),
        "quantity": quantity,
        "amount": amount,
    }


def fetch_data():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/145 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com/",
    }

    response = requests.get(URL, headers=headers, timeout=30)
    response.raise_for_status()

    # 네이버 금융의 한글 페이지는 EUC-KR/CP949 계열인 경우가 있습니다.
    response.encoding = response.apparent_encoding or "euc-kr"
    soup = BeautifulSoup(response.text, "html.parser")

    target_table = None

    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        companies = table.select("a.company")

        if (
            "순매도상위" in text
            and "순매수상위" in text
            and len(companies) >= 10
        ):
            target_table = table
            break

    if target_table is None:
        raise RuntimeError(
            "네이버 표를 찾지 못했습니다. "
            "네이버 페이지 구조가 변경되었을 가능성이 있습니다."
        )

    order = group_order(target_table)
    result = {"buy": [], "sell": []}

    for row in target_table.find_all("tr"):
        cells = row.find_all("td")
        company_positions = [
            i for i, cell in enumerate(cells)
            if cell.select_one("a.company")
        ]

        if len(company_positions) < 2:
            continue

        first_start = company_positions[0]
        second_start = company_positions[1]

        first = parse_group(cells, first_start, second_start)
        second = parse_group(cells, second_start, len(cells))

        if first:
            result[order[0]].append(first)

        if second:
            result[order[1]].append(second)

    result["buy"] = result["buy"][:10]
    result["sell"] = result["sell"][:10]

    if not result["buy"] or not result["sell"]:
        raise RuntimeError(
            "종목을 충분히 읽지 못했습니다. "
            "Actions 실행 화면의 오류 내용을 확인해 주세요."
        )

    for key in ("buy", "sell"):
        for rank, item in enumerate(result[key], start=1):
            item["rank"] = rank

    result["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    result["source"] = URL
    result["unit"] = "네이버 표 표시 단위"

    return result


def main():
    data = fetch_data()

    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"저장 완료: {data['updated_at']}")
    print("순매수:", [item["name"] for item in data["buy"]])
    print("순매도:", [item["name"] for item in data["sell"]])


if __name__ == "__main__":
    main()
