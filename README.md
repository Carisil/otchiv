# otchiv — 로또 6/45 당첨번호 데이터

GitHub Actions + Playwright로 동행복권에서 당첨번호를 자동 수집하여 GitHub Pages로 서빙.

## 데이터 접근

| 엔드포인트 | URL |
|-----------|-----|
| 전체 이력 | `https://carisil.github.io/otchiv/data/all.json` |
| 최신 회차 | `https://carisil.github.io/otchiv/data/latest.json` |

## JSON 형식

```json
{
  "round": 1214,
  "date": "2026-03-07",
  "numbers": [10, 15, 19, 27, 30, 33],
  "bonus": 14
}
```

## 갱신 주기

매주 토요일 23:00 KST 자동 실행. 실패 시 1시간 간격 재시도 (최대 2회).
