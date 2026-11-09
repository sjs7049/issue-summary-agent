"""v1과 v2의 재시도 결과를 나란히 비교한다.

각 기사의 '마지막 시도'를 최종 결과로 본다.
"""
import json


def final_rows(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    last = {}
    for r in rows:  # 같은 기사는 뒤의 시도가 앞의 것을 덮어쓴다
        last[r["id"]] = r
    return last


v1 = final_rows("feedback_db.json")
v2 = final_rows("feedback_db_v2.json")

print(f"{'종목':<16}{'v1 R1/RL':>14}{'v1 판정':>16}{'v2 R1/RL':>14}{'v2 판정':>16}  v2 진단")
for i in sorted(v1):
    a, b = v1[i], v2.get(i)
    if not b:
        continue
    print(f"{a['stock'][:14]:<16}"
          f"{a['rouge1']:>7}/{a['rougeL']:<6}{a['status']:>16}"
          f"{b['rouge1']:>7}/{b['rougeL']:<6}{b['status']:>16}  {b.get('diagnosis', '')}")

approved = lambda d: sum(1 for r in d.values() if r["status"] == "Approved")
print(f"\nApproved: v1 {approved(v1)}개 → v2 {approved(v2)}개 (전체 {len(v1)}개)")
