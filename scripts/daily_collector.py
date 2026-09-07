import json
import os
import sys
import time
from datetime import datetime, date, timedelta, timezone
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

# 한국 표준시 (KST = UTC+9) 정의
KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://gall.dcinside.com/",
}

def parse_article_date(date_td) -> date | None:
    full_date_str = date_td.get("title", "").strip()
    if full_date_str:
        try:
            return datetime.strptime(full_date_str, "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            pass

    raw_text = date_td.get_text(strip=True)
    # 한국 시간 기준 오늘 날짜
    today = datetime.now(KST).date()

    if ":" in raw_text:
        return today

    parts = raw_text.split(".")
    if len(parts) == 3:
        year_part = parts[0]
        year = 2000 + int(year_part) if len(year_part) == 2 else int(year_part)
        return date(year, int(parts[1]), int(parts[2]))
    if len(parts) == 2:
        return date(today.year, int(parts[0]), int(parts[1]))

    return None

def count_single_day_posts(gallery_id: str, keyword: str, target_day: date, is_mini: bool = True) -> int:
    prefix = "mini/board/lists/" if is_mini else "board/lists/"
    base_url = f"https://gall.dcinside.com/{prefix}"
    encoded_keyword = quote(keyword.encode("utf-8"))

    session = requests.Session()
    session.headers.update(HEADERS)

    count = 0
    page = 1
    consecutive_outdated = 0

    print(f"[{target_day}] 집계 시작 - 키워드: '{keyword}' (갤러리: {gallery_id})")

    while True:
        target_url = (
            f"{base_url}?id={gallery_id}"
            f"&s_type=search_subject"
            f"&s_keyword={encoded_keyword}"
            f"&page={page}"
        )

        try:
            res = session.get(target_url, timeout=10)
            res.raise_for_status()
        except requests.RequestException as e:
            print(f"[경고] {page}페이지 요청 실패: {e}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        post_rows = soup.select("tr.ub-content.us-post")
        if not post_rows:
            break

        for row in post_rows:
            num_td = row.select_one("td.gall_num")
            if not num_td or not num_td.get_text(strip=True).isdigit():
                continue

            date_td = row.select_one("td.gall_date")
            if not date_td:
                continue

            post_date = parse_article_date(date_td)
            if not post_date:
                continue

            title_td = row.select_one("td.gall_tit a")
            post_title = title_td.get_text(strip=True) if title_td else ""
            if keyword.lower() not in post_title.lower():
                continue

            if post_date > target_day:
                continue
            elif post_date < target_day:
                consecutive_outdated += 1
                if consecutive_outdated >= 10:
                    print(f"[{page}페이지] 대상일({target_day}) 이전 글 도달. 집계 완료.")
                    return count
            else:
                consecutive_outdated = 0
                count += 1

        page += 1
        time.sleep(0.8)

    return count

def update_json_data(data_file: str, target_day: date, count: int, gallery_id: str, keyword: str):
    os.makedirs(os.path.dirname(data_file), exist_ok=True)

    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"gallery_id": gallery_id, "keyword": keyword, "records": []}
    else:
        data = {"gallery_id": gallery_id, "keyword": keyword, "records": []}

    target_str = str(target_day)
    records = data.get("records", [])
    existing = next((r for r in records if r["date"] == target_str), None)
    if existing:
        existing["count"] = count
    else:
        records.append({"date": target_str, "count": count})

    records.sort(key=lambda x: x["date"])
    data["records"] = records
    # 한국 시간 기준 타임스탬프 기록
    data["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"-> {target_str}: {count}건 업데이트 완료 ({data_file})")

def main():
    gallery_id = "remini"
    keyword = "리센느미니"
    data_file = "data/daily_counts.json"

    # 한국 표준시(KST) 기준 어제 날짜 계산
    now_kst = datetime.now(KST)
    yesterday = (now_kst - timedelta(days=1)).date()

    if len(sys.argv) > 1:
        yesterday = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()

    count = count_single_day_posts(
        gallery_id=gallery_id,
        keyword=keyword,
        target_day=yesterday,
        is_mini=True
    )

    update_json_data(data_file, yesterday, count, gallery_id, keyword)

if __name__ == "__main__":
    main()
