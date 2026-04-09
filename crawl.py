"""
로또 6/45 당첨번호 크롤러 v2
Playwright로 네트워크 요청을 가로채서 데이터를 수집한다.
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


def fetch_round_playwright(context, round_no):
    """Playwright 페이지에서 특정 회차 데이터 가져오기"""
    captured = {}

    def handle_response(response):
        """네트워크 응답 가로채기"""
        url = response.url
        if "getLottoNumber" in url or "selectPstLt645" in url or "lotto" in url.lower():
            try:
                body = response.text()
                if body.strip().startswith("{"):
                    data = json.loads(body)
                    captured["api"] = data
                    print(f"    API 응답 캡처: {url[:80]}")
            except Exception:
                pass

    page = context.new_page()
    page.on("response", handle_response)

    try:
        # 메인 페이지 방문 (JS 챌린지 통과)
        page.goto("https://www.dhlottery.co.kr/", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 방법 1: 기존 API를 JS에서 직접 호출
        result = page.evaluate(f"""
            async () => {{
                try {{
                    const resp = await fetch(
                        'https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={round_no}',
                        {{
                            headers: {{
                                'X-Requested-With': 'XMLHttpRequest',
                                'Accept': 'application/json'
                            }}
                        }}
                    );
                    const text = await resp.text();
                    if (text.trim().startsWith('{{')) return JSON.parse(text);
                    return {{'error': 'not json', 'status': resp.status, 'preview': text.substring(0, 200)}};
                }} catch(e) {{
                    return {{'error': e.message}};
                }}
            }}
        """)

        if result and result.get("returnValue") == "success":
            data = result
            page.close()
            return {
                "round": data["drwNo"],
                "date": data["drwNoDate"],
                "numbers": sorted([data[f"drwtNo{i}"] for i in range(1, 7)]),
                "bonus": data["bnusNo"],
            }

        print(f"    방법1(fetch API) 결과: {json.dumps(result, ensure_ascii=False)[:150]}")

        # 방법 2: 결과 페이지로 이동해서 DOM에서 추출
        page.goto("https://www.dhlottery.co.kr/lt645/result", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # 페이지 내 번호 추출 시도 (여러 셀렉터)
        for selector_set in [
            {"balls": ".ball_645", "bonus": ".bonus"},
            {"balls": "[class*='ball']", "bonus": "[class*='bonus']"},
            {"balls": ".num", "bonus": ".bonus_num"},
            {"balls": "span.ball", "bonus": "span.bonus"},
        ]:
            balls = page.query_selector_all(selector_set["balls"])
            if len(balls) >= 6:
                nums = []
                for b in balls[:6]:
                    text = b.text_content().strip()
                    if text.isdigit():
                        nums.append(int(text))
                if len(nums) == 6:
                    bonus_el = page.query_selector(selector_set["bonus"])
                    bonus = int(bonus_el.text_content().strip()) if bonus_el else 0
                    page.close()
                    return {
                        "round": round_no,
                        "date": "",
                        "numbers": sorted(nums),
                        "bonus": bonus,
                    }

        # 방법 3: 전체 HTML에서 regex로 번호 패턴 추출
        html = page.content()
        import re
        # "당첨번호" 근처의 숫자들
        num_blocks = re.findall(r'>(\d{1,2})<', html)
        valid_nums = [int(n) for n in num_blocks if 1 <= int(n) <= 45]

        # 디버깅: 페이지 제목과 URL 출력
        print(f"    페이지 제목: {page.title()}")
        print(f"    페이지 URL: {page.url}")
        print(f"    DOM에서 찾은 1~45 숫자 개수: {len(valid_nums)}")
        if valid_nums:
            print(f"    처음 20개: {valid_nums[:20]}")

        # 디버깅: 캡처된 API 응답 출력
        if captured:
            print(f"    캡처된 API: {json.dumps(captured, ensure_ascii=False)[:200]}")

        page.close()
        return None

    except Exception as e:
        print(f"    Playwright 오류: {e}")
        try:
            page.close()
        except Exception:
            pass
        return None


def main():
    existing = load_existing()
    last_round = max((r["round"] for r in existing), default=0)
    print(f"기존 데이터: {len(existing)}회차 (최신: {last_round}회차)")

    new_rounds = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 720},
        )

        round_no = last_round + 1
        failures = 0

        print(f"\n{round_no}회차부터 수집 시작...")
        while failures < 3:
            print(f"\n  [{round_no}회차]")
            data = fetch_round_playwright(context, round_no)
            if data:
                new_rounds.append(data)
                print(f"  -> 성공!")
                failures = 0
                round_no += 1
                time.sleep(1)
            else:
                print(f"  -> 실패")
                failures += 1
                round_no += 1

        browser.close()

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
