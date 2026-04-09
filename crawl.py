"""
로또 6/45 당첨번호 크롤러
Playwright로 동행복권 사이트의 JS 챌린지를 통과한 후 데이터를 수집한다.

사용법: python crawl.py
결과: data/all.json, data/latest.json
"""
import json
import os
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright

DATA_DIR = "data"
ALL_JSON = os.path.join(DATA_DIR, "all.json")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")

API_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={}"
SITE_URL = "https://www.dhlottery.co.kr/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.dhlottery.co.kr/",
    "X-Requested-With": "XMLHttpRequest",
}


def load_existing():
    try:
        with open(ALL_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_data(all_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    all_data.sort(key=lambda x: x["round"])
    with open(ALL_JSON, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False)
    if all_data:
        with open(LATEST_JSON, "w", encoding="utf-8") as f:
            json.dump(all_data[-1], f, ensure_ascii=False, indent=2)


def get_session_cookies():
    """Playwright로 동행복권 접속 후 세션 쿠키 획득"""
    print("브라우저로 세션 쿠키 획득 중...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.goto(SITE_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)
        cookies = context.cookies()
        browser.close()
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    print(f"  쿠키 {len(cookie_dict)}개 획득")
    return cookie_dict


def fetch_via_api(session, round_no):
    """세션 쿠키로 기존 API 호출"""
    try:
        resp = session.get(API_URL.format(round_no), headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        text = resp.text.strip()
        if not text.startswith("{"):
            return None
        data = resp.json()
        if data.get("returnValue") != "success":
            return None
        return {
            "round": data["drwNo"],
            "date": data["drwNoDate"],
            "numbers": sorted([data[f"drwtNo{i}"] for i in range(1, 7)]),
            "bonus": data["bnusNo"],
        }
    except Exception as e:
        print(f"  API 실패 (round={round_no}): {e}")
        return None


def fetch_via_scrape(round_no):
    """Playwright로 결과 페이지 스크래핑"""
    print(f"  스크래핑 시도 (round={round_no})...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()

            # 메인 페이지로 쿠키 획득
            page.goto(SITE_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 결과 페이지 이동
            page.goto(
                "https://www.dhlottery.co.kr/lt645/result",
                wait_until="networkidle",
                timeout=30000,
            )
            time.sleep(3)

            # 회차 입력 시도
            for sel in ['input[name="drwNo"]', 'input[id*="drwNo"]', 'input[type="text"]']:
                el = page.query_selector(sel)
                if el:
                    el.fill(str(round_no))
                    break

            # 조회 버튼 클릭
            for sel in ['button:has-text("조회")', 'a:has-text("조회")', 'button[type="submit"]']:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    break

            page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(2)
            html = page.content()
            browser.close()

            # 번호 파싱
            ball_numbers = re.findall(r'class="[^"]*ball[^"]*"[^>]*>(\d{1,2})<', html)
            if len(ball_numbers) >= 7:
                nums = [int(n) for n in ball_numbers[:6]]
                bonus = int(ball_numbers[6])
                date_match = re.search(r'(\d{4}[-./]\d{2}[-./]\d{2})', html)
                date_str = date_match.group(1).replace(".", "-").replace("/", "-") if date_match else ""
                return {
                    "round": round_no,
                    "date": date_str,
                    "numbers": sorted(nums),
                    "bonus": bonus,
                }
    except Exception as e:
        print(f"  스크래핑 실패 (round={round_no}): {e}")
    return None


def main():
    existing = load_existing()
    last_round = max((r["round"] for r in existing), default=0)
    print(f"기존 데이터: {len(existing)}회차 (최신: {last_round}회차)")

    # 방법 1: 세션 쿠키 + API
    cookies = get_session_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    new_rounds = []
    round_no = last_round + 1
    failures = 0

    print(f"\n{round_no}회차부터 API 수집...")
    while failures < 3:
        data = fetch_via_api(session, round_no)
        if data:
            new_rounds.append(data)
            print(f"  {round_no}회차 OK")
            failures = 0
            round_no += 1
            time.sleep(0.5)
        else:
            failures += 1
            round_no += 1

    # 방법 2: API 실패 시 스크래핑
    if not new_rounds:
        print("\nAPI 실패. 스크래핑 시도...")
        round_no = last_round + 1
        for _ in range(5):
            data = fetch_via_scrape(round_no)
            if data:
                new_rounds.append(data)
                print(f"  {round_no}회차 스크래핑 OK")
                round_no += 1
                time.sleep(1)
            else:
                break

    if not new_rounds:
        print("\n신규 데이터 없음")
        return False

    all_data = existing + new_rounds
    save_data(all_data)
    print(f"\n완료: +{len(new_rounds)}회차, 총 {len(all_data)}회차")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
