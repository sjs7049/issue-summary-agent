"""5단계 v2: 실패 원인에 맞춰 재시도하는 피드백 루프

v1에서 발견한 문제와 v2의 대응
  1. 실패 원인을 잘못 짚었다 (정밀도 0.603 < 재현율 0.613처럼 0.01 차이로 '너무 길다'고 판단)
     → 어느 지표가 떨어졌는지 먼저 보고, 정밀도·재현율은 0.05 이상 차이 날 때만 쓴다.
  2. 모델이 글자 수 지시를 지키지 않았다 ('251자 안팎' → 316자)
     → 코드로 길이를 재서, 기준 요약의 1.2배를 넘으면 한 번 더 줄이라고 요청한다.
  3. temperature 0.7은 품질이 아니라 무작위성만 늘렸다
     → 재시도도 0.2로 유지하고, 지시 내용만 바꾼다.

1차 요약은 v1과 똑같이 summaries.json을 써서, 재시도 방식만 비교한다.
결과는 feedback_db_v2.json에 저장한다.

실행: python feedback_loop_v2.py          → 미달마다 사람이 선택
      python feedback_loop_v2.py --auto   → 묻지 않고 항상 재시도
"""
import json
import sys
import time
from datetime import datetime

from rouge_eval import ROUGE1_THRESHOLD, ROUGEL_THRESHOLD, evaluate
from summarize import summarize

AUTO = "--auto" in sys.argv
TEMPERATURE = 0.2       # v1은 재시도에 0.7을 썼다
GAP = 0.05              # 정밀도와 재현율이 이만큼 차이 날 때만 한쪽 문제로 본다
LENGTH_LIMIT = 1.2      # 기준 요약 길이의 1.2배까지 허용

with open("summaries.json", encoding="utf-8") as f:
    CACHED = {s["id"]: s["summary"] for s in json.load(f)}

ORDER_INSTRUCTION = (
    "내용은 유지하되 다음 순서로 다시 써라. "
    "(1) 종목명, 등락률, 주가 (2) 주가가 움직인 직접 원인 "
    "(3) 원인을 뒷받침하는 핵심 수치 (4) 주의할 점. 한 문장에는 한 가지 내용만 담아라."
)


def diagnose(score):
    """1차 점수를 보고 실패 원인과 재시도 지시를 정한다."""
    r1_ok = score["rouge1"] >= ROUGE1_THRESHOLD
    rl_ok = score["rougeL"] >= ROUGEL_THRESHOLD
    gap = score["precision"] - score["recall"]

    if r1_ok and not rl_ok:
        # 단어는 충분히 겹치는데 순서가 다르다 → 흐름 문제
        return "순서", ORDER_INSTRUCTION
    if gap <= -GAP:
        # 모델 요약에만 있는 단어가 많다 → 군더더기
        return "군더더기", ("주가 변동의 직접 원인과 관련 없는 부가 정보(다른 사업 소식, 업종 분위기 등)는 빼고, "
                          "직접 원인과 그 근거만 남겨라.")
    if gap >= GAP:
        # 기준 요약의 단어를 많이 놓쳤다 → 누락
        return "누락", "기사의 핵심 원인과 주요 수치(등락률, 주가, 실적 등)를 빠뜨리지 말고 모두 포함하라."
    # 어느 한쪽 문제라고 보기 어렵다 → 순서를 잡으면서 직접 원인에 집중
    return "복합", ORDER_INSTRUCTION + " 직접 원인과 관련 없는 내용은 빼라."


def summarize_within_length(article, instruction, limit):
    """요약을 만들고, 길이를 코드로 확인한다. 넘치면 한 번 더 줄이라고 요청한다."""
    summary = summarize(article, temperature=TEMPERATURE, extra_instruction=instruction)
    if len(summary) <= limit:
        return summary, False
    print(f"  {len(summary)}자로 제한({limit}자)을 넘어 한 번 더 줄입니다...", flush=True)
    time.sleep(5)
    shorter = (f"{instruction} 반드시 {limit}자 이하로 써라. "
               f"방금 쓴 요약은 {len(summary)}자라 너무 길었다.")
    return summarize(article, temperature=TEMPERATURE, extra_instruction=shorter), True


def ask_human(article, summary, score, reason):
    if AUTO:
        return "r"
    print(f"\n--- [{article['id']}] {article['stock']} 1차 요약 (기준 미달, 진단: {reason}) ---")
    print(summary)
    print(f"ROUGE-1 {score['rouge1']} / ROUGE-L {score['rougeL']} "
          f"(정밀도 {score['precision']}, 재현율 {score['recall']})")
    while True:
        choice = input("r = 재시도, s = 중단하고 수동 검토로 보내기 > ").strip().lower()
        if choice in ("r", "s"):
            return choice


def log(db, article, attempt, reason, instruction, summary, score, status, length_fixed=False):
    db.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "id": article["id"],
        "stock": article["stock"],
        "attempt": attempt,
        "temperature": TEMPERATURE,
        "diagnosis": reason,
        "instruction": instruction,
        "length_fixed": length_fixed,
        "summary": summary,
        "length": len(summary),
        **{k: score[k] for k in ("rouge1", "rougeL", "precision", "recall")},
        "status": status,
    })


def run(article, db):
    ref = article["reference_summary"]
    limit = int(len(ref) * LENGTH_LIMIT)

    # 1차: v1과 같은 요약
    print(f"[{article['id']}] {article['stock']} 1차 평가 중...", flush=True)
    summary = CACHED.get(article["id"]) or summarize(article, temperature=TEMPERATURE)
    score = evaluate(summary, ref)
    if score["passed"]:
        log(db, article, 1, "", "", summary, score, "Approved")
        return "Approved", 1

    reason, instruction = diagnose(score)
    if ask_human(article, summary, score, reason) == "s":
        log(db, article, 1, reason, "", summary, score, "Human_Rejected")
        return "Human_Rejected", 1
    log(db, article, 1, reason, "", summary, score, "Retry")

    # 2차: 진단에 맞춘 지시 + 길이 확인
    time.sleep(5)
    print(f"재시도 중... (진단: {reason})", flush=True)
    summary, fixed = summarize_within_length(article, instruction, limit)
    score = evaluate(summary, ref)
    status = "Approved" if score["passed"] else "Rejected"
    print(f"--- 2차 요약 ({len(summary)}자) → {status} ---")
    print(summary)
    print(f"ROUGE-1 {score['rouge1']} / ROUGE-L {score['rougeL']} "
          f"(정밀도 {score['precision']}, 재현율 {score['recall']})", flush=True)
    log(db, article, 2, reason, instruction, summary, score, status, fixed)
    return status, 2


if __name__ == "__main__":
    with open("news.json", encoding="utf-8") as f:
        articles = json.load(f)

    db, results = [], []
    for a in articles:
        status, attempts = run(a, db)
        results.append((a["stock"], status, attempts))
        with open("feedback_db_v2.json", "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        time.sleep(5)

    print("\n[최종 결과]")
    for stock, status, attempts in results:
        print(f" - {stock[:14]:<16} {status:<15} (시도 {attempts}회)")
    print("\n모든 시도를 feedback_db_v2.json에 저장했습니다. python compare.py로 v1과 비교하세요.")
