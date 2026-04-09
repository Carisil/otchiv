"""
로또 6/45 당첨번호 크롤러 v3
Playwright로 동행복권 결과 페이지를 열고, 내부 API 응답을 가로채서 데이터를 수집한다.
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

DATA_DIR = "data"
ALL_JSON = os.path.join(DATA_DIR, "all.json")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


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


def parse_api_item(item):
    """새 내부 API 응답의 한 항목을 DrawResult 형식으로 변환"""
    try:
        round_no = item.get("ltEpsd")
        if not round_no:
            return None

        numbers = []
        for i in range(1, 7):
            n = item.get(f"tm{i}WnNo")
            if n is not None:
                numbers.append(int(n))
        if len(numbers) != 6:
            return None

        bonus = item.get("bnusNo") or item.get("bonusNo") or item.get("tm7WnNo") or 0

        date_str = item.get("drwNoDate") or item.get("drawDate") or item.get("crDt") or ""
        if date_str and "T" in date_str:
            date_str = date_str.split("T")[0]

        return {
            "round": int(round_no),
            "date": date_str,
            "numbers": sorted(numbers),
            "bonus": int(bonus),
        }
    except Exception as e:
        print(f"    파싱 오류: {e}")
        return None


def crawl_with_playwright(existing_rounds):
    """Playwright로 결과 페이지를 열고 내부 API 응답을 수집"""
    captured_items = []

    def handle_response(response):
        url = response.url
        if "selectPstLt645" in url:
            try:
                body = response.text()
                if body.strip().startswith("{"):
                    data = json.loads(body)
                    items = data.get("data", {}).get("list", [])
                    for item in items:
                        parsed = parse_api_item(item)
                        if parsed and parsed["round"] not in existing_rounds:
                            captured_items.append(parsed)
                            print(f"    캡처: {parsed['round']}회차 {parsed['numbers']} +{parsed['bonus']}")
            except Exception as e:
                print(f"    응답 파싱 실패: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.on("response", handle_response)

        # 메인 페이지 → JS 챌린지 통과
        print("메인 페이지 접속 중...")
        page.goto("https://www.dhlottery.co.kr/", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 결과 페이지 → 내부 API 자동 호출됨
        print("결과 페이지 접속 중...")
        page.goto("https://www.dhlottery.co.kr/lt645/result", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # 이전/다음 페이지 네비게이션으로 더 많은 회차 수집 시도
        for direction in ["prev", "prev", "prev", "prev", "prev"]:
            try:
                btn = page.query_selector(f'a:has-text("이전"), button:has-text("이전"), [class*="{direction}"]')
                if btn:
                    btn.click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)
            except Exception:
                break

        browser.close()

    return captured_items


def main():
    existing = load_existing()
    existing_rounds = {r["round"] for r in existing}
    last_round = max(existing_rounds, default=0)
    print(f"기존 데이터: {len(existing)}회차 (최신: {last_round}회차)")

    print("\nPlaywright 크롤링 시작...")
    new_rounds = crawl_with_playwright(existing_rounds)

    # 중복 제거
    seen = set()
    unique_new = []
    for r in new_rounds:
        if r["round"] not in seen and r["round"] not in existing_rounds:
            seen.add(r["round"])
            unique_new.append(r)

    if not unique_new:
        print("\n신규 데이터 없음")
        return False

    all_data = existing + unique_new
    save_data(all_data)
    print(f"\n완료: +{len(unique_new)}회차, 총 {len(all_data)}회차")
    for r in sorted(unique_new, key=lambda x: x["round"]):
        print(f"  {r['round']}회차: {r['numbers']} +{r['bonus']} ({r['date']})")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
