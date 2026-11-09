"""2단계: news.json 점검

빈 칸, 너무 짧은 본문, 기준 요약 길이를 확인한다.
모든 기사가 OK가 나오면 3단계로 넘어간다.
"""
import json

REQUIRED = ["stock", "change_rate", "title", "body", "link", "published", "reference_summary"]

with open("news.json", encoding="utf-8") as f:
    articles = json.load(f)

all_ok = True
for a in articles:
    problems = []

    # 빈 칸이 있는지
    for key in REQUIRED:
        if not str(a.get(key, "")).strip():
            problems.append(f"{key} 비어 있음")

    # 본문이 너무 짧으면 요약할 거리가 없다
    body_len = len(a.get("body", ""))
    if 0 < body_len < 300:
        problems.append(f"본문이 {body_len}자로 짧음 (300자 이상 권장)")

    # 기준 요약은 모델 요약(400자 이내)과 비슷한 길이여야 비교가 공정하다
    ref_len = len(a.get("reference_summary", ""))
    if ref_len and not (200 <= ref_len <= 400):
        problems.append(f"기준 요약이 {ref_len}자 (200~400자 권장)")

    status = "OK" if not problems else " / ".join(problems)
    print(f"[{a['id']}] {a.get('stock') or '(종목 없음)'}: 본문 {body_len}자, 기준 요약 {ref_len}자 → {status}")
    all_ok = all_ok and not problems

print("\n모두 준비됐습니다. 3단계로 넘어가세요." if all_ok else "\n위 문제를 고친 뒤 다시 실행하세요.")
