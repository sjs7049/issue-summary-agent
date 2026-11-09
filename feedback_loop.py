"""5단계: 피드백 루프 (제안서 14쪽 '이슈 요약 피드백 노드'를 구현)

흐름
  1차 요약 → ROUGE 평가
    ├─ 통과 → Approved
    └─ 미달 → HITL 분기: 사람이 고른다
          ├─ r (재시도) → 파라미터와 지시를 바꿔 2차 요약 → 평가
          │     ├─ 통과 → Approved
          │     └─ 미달 → Rejected (2회 실패, 수동 검토 대상)
          └─ s (중단) → Human_Rejected (수동 검토 대상)

모든 시도는 feedback_db.json에 쌓인다 (제안서의 '모델 개선용 피드백 DB').

실행: python feedback_loop.py          → 미달마다 사람이 선택
      python feedback_loop.py --auto   → 묻지 않고 항상 재시도
      python feedback_loop.py --fresh  → 1차 요약도 새로 만든다 (기본은 summaries.json 재사용)
"""
import json
import sys
import time
from datetime import datetime

from rouge_eval import evaluate
from summarize import summarize

AUTO = "--auto" in sys.argv
FRESH = "--fresh" in sys.argv

# 무료 등급 요청 수를 아끼려고, 1차 요약은 summarize.py로 이미 만든 것을 다시 쓴다
CACHED = {}
if not FRESH:
    try:
        with open("summaries.json", encoding="utf-8") as f:
            CACHED = {s["id"]: s["summary"] for s in json.load(f)}
    except FileNotFoundError:
        pass
FIRST_TEMPERATURE = 0.2
RETRY_TEMPERATURE = 0.7  # 제안서의 '파라미터를 바꿔 재시도'


def retry_instruction(score, reference_len):
    """1차 점수를 보고 무엇을 고칠지 정한다.
    정밀도가 낮으면 군더더기가 많은 것이고, 재현율이 낮으면 핵심을 빠뜨린 것이다.
    """
    if score["precision"] < score["recall"]:
        return (f"요약이 너무 길거나 부가 정보가 많다. {reference_len}자 안팎으로 줄이고, "
                "주가 변동의 직접 원인과 핵심 수치만 남겨라.")
    return "기사의 핵심 원인과 주요 수치(등락률, 주가, 실적 등)를 빠뜨리지 말고 모두 포함하라."


def ask_human(article, summary, score):
    """HITL 분기: 사람이 요약을 보고 재시도할지 정한다."""
    if AUTO:
        return "r"
    print(f"\n--- [{article['id']}] {article['stock']} 1차 요약 (기준 미달) ---")
    print(summary)
    print(f"ROUGE-1 {score['rouge1']} / ROUGE-L {score['rougeL']} "
          f"(정밀도 {score['precision']}, 재현율 {score['recall']})")
    while True:
        choice = input("r = 재시도, s = 중단하고 수동 검토로 보내기 > ").strip().lower()
        if choice in ("r", "s"):
            return choice


def log(db, article, attempt, temperature, instruction, summary, score, status):
    db.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "id": article["id"],
        "stock": article["stock"],
        "attempt": attempt,
        "temperature": temperature,
        "instruction": instruction,
        "summary": summary,
        "length": len(summary),
        **{k: score[k] for k in ("rouge1", "rougeL", "precision", "recall")},
        "status": status,
    })


def run(article, db):
    ref = article["reference_summary"]

    # 1차 시도 (저장된 요약이 있으면 API를 부르지 않는다)
    print(f"[{article['id']}] {article['stock']} 1차 평가 중...", flush=True)
    summary = CACHED.get(article["id"]) or summarize(article, temperature=FIRST_TEMPERATURE)
    score = evaluate(summary, ref)
    if score["passed"]:
        log(db, article, 1, FIRST_TEMPERATURE, "", summary, score, "Approved")
        return "Approved", 1

    # HITL 분기
    if ask_human(article, summary, score) == "s":
        log(db, article, 1, FIRST_TEMPERATURE, "", summary, score, "Human_Rejected")
        return "Human_Rejected", 1
    log(db, article, 1, FIRST_TEMPERATURE, "", summary, score, "Retry")

    # 2차 시도: 파라미터와 지시를 바꾼다
    time.sleep(5)
    instruction = retry_instruction(score, len(ref))
    print(f"재시도 중... (temperature {RETRY_TEMPERATURE}, 지시: {instruction})", flush=True)
    summary = summarize(article, temperature=RETRY_TEMPERATURE, extra_instruction=instruction)
    score = evaluate(summary, ref)
    status = "Approved" if score["passed"] else "Rejected"
    print(f"--- 2차 요약 ({len(summary)}자) → {status} ---")
    print(summary)
    print(f"ROUGE-1 {score['rouge1']} / ROUGE-L {score['rougeL']} "
          f"(정밀도 {score['precision']}, 재현율 {score['recall']})", flush=True)
    log(db, article, 2, RETRY_TEMPERATURE, instruction, summary, score, status)
    return status, 2


if __name__ == "__main__":
    with open("news.json", encoding="utf-8") as f:
        articles = json.load(f)

    db, results = [], []
    for a in articles:
        status, attempts = run(a, db)
        results.append((a["stock"], status, attempts))
        # 기사마다 바로 저장해서, 중간에 멈춰도 지금까지의 기록은 남긴다
        with open("feedback_db.json", "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        time.sleep(5)  # 무료 등급 요청 제한을 피하려고 기사 사이에 쉰다

    print("\n[최종 결과]")
    for stock, status, attempts in results:
        print(f" - {stock[:14]:<16} {status:<15} (시도 {attempts}회)")
    print("\n모든 시도를 feedback_db.json에 저장했습니다.")