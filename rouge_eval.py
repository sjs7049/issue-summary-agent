"""4단계: ROUGE 평가 노드

모델 요약(summaries.json)을 내가 쓴 기준 요약(news.json)과 비교해
ROUGE-1, ROUGE-L 점수를 낸다. 라이브러리 없이 직접 계산한다.

한국어는 조사가 붙어 '박셀바이오는'과 '박셀바이오가'를 다른 단어로 본다.
그래서 두 가지 토큰화로 점수를 비교한다.
  - 어절: 띄어쓰기 단위
  - 형태소: Kiwi 형태소 분석기로 조사·어미를 떼어낸 단위
"""
import json
import re
from collections import Counter

from kiwipiepy import Kiwi

kiwi = Kiwi()

# 제안서 기준값은 ROUGE-1 0.55, ROUGE-L 0.50 (See et al., 2017 참고)이었다.
# 실습해 보니 내용이 정확한 요약도 ROUGE-L 0.5를 거의 넘지 못했다.
# 영어 데이터 기준값이라 한국어 형태소 기준에 맞게 ROUGE-L만 0.40으로 낮췄다.
ROUGE1_THRESHOLD = 0.55
ROUGEL_THRESHOLD = 0.40


# ---------- 토큰화 ----------
def tokenize_eojeol(text):
    """어절 단위: 문장부호를 지우고 띄어쓰기로 나눈다."""
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 4,835 → 4835 (천 단위 쉼표 제거)
    text = re.sub(r"[^\w\s%.]", " ", text)   # %, 소수점은 숫자 표현이라 남긴다
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # 숫자 사이가 아닌 마침표는 지운다
    return text.split()


def tokenize_morph(text):
    """형태소 단위: 의미를 가진 품사만 남긴다.
    N=명사, V=동사·형용사 어간, SN=숫자, SL=영어, MAG=부사, XR=어근
    조사(J), 어미(E), 문장부호(S*)는 버린다.
    """
    keep = ("N", "V", "SN", "SL", "MAG", "XR")
    return [t.form for t in kiwi.tokenize(text) if t.tag.startswith(keep)]


# ---------- ROUGE 계산 ----------
def f1(precision, recall):
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def rouge_1(candidate, reference):
    """겹치는 단어 수로 정밀도·재현율·F1을 계산한다.
    정밀도 = 겹친 수 / 모델 요약 단어 수 (군더더기가 적은가)
    재현율 = 겹친 수 / 기준 요약 단어 수 (핵심을 빠뜨리지 않았나)
    """
    cand, ref = Counter(candidate), Counter(reference)
    overlap = sum((cand & ref).values())  # 같은 단어는 양쪽 중 적은 횟수만큼만 센다
    p = overlap / len(candidate) if candidate else 0.0
    r = overlap / len(reference) if reference else 0.0
    return p, r, f1(p, r)


def lcs_length(a, b):
    """최장 공통 부분수열(LCS) 길이. 순서를 지키며 겹치는 단어 수다.
    dp[i][j] = a의 앞 i개와 b의 앞 j개 사이의 LCS 길이
    """
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def rouge_l(candidate, reference):
    """LCS로 정밀도·재현율·F1을 계산한다. 단어의 순서(문장 흐름)까지 본다."""
    lcs = lcs_length(candidate, reference)
    p = lcs / len(candidate) if candidate else 0.0
    r = lcs / len(reference) if reference else 0.0
    return f1(p, r)


def evaluate(summary, reference, tokenizer=tokenize_morph):
    """요약 하나를 평가해 점수와 통과 여부를 돌려준다. 5단계에서 다시 쓴다."""
    cand, ref = tokenizer(summary), tokenizer(reference)
    p, r, r1 = rouge_1(cand, ref)
    rl = rouge_l(cand, ref)
    passed = r1 >= ROUGE1_THRESHOLD and rl >= ROUGEL_THRESHOLD
    return {
        "rouge1": round(r1, 3),
        "rougeL": round(rl, 3),
        "precision": round(p, 3),  # 낮으면 기준에 없는 내용이 많다 (군더더기)
        "recall": round(r, 3),     # 낮으면 기준의 핵심을 빠뜨렸다
        "passed": passed,
    }


if __name__ == "__main__":
    with open("news.json", encoding="utf-8") as f:
        references = {a["id"]: a["reference_summary"] for a in json.load(f)}
    with open("summaries.json", encoding="utf-8") as f:
        summaries = json.load(f)

    print(f"기준값: ROUGE-1 ≥ {ROUGE1_THRESHOLD}, ROUGE-L ≥ {ROUGEL_THRESHOLD}\n")
    print(f"{'종목':<16}{'어절 R1':>8}{'어절 RL':>8}{'형태소 R1':>10}{'형태소 RL':>10}  판정(형태소)")
    for s in summaries:
        ref = references[s["id"]]
        e = evaluate(s["summary"], ref, tokenize_eojeol)
        m = evaluate(s["summary"], ref, tokenize_morph)
        verdict = "Approved" if m["passed"] else "Rejected"
        print(f"{s['stock'][:14]:<16}{e['rouge1']:>8}{e['rougeL']:>8}{m['rouge1']:>10}{m['rougeL']:>10}  {verdict}")

    # 토큰화가 어떻게 다른지 첫 문장으로 확인
    sample = summaries[0]["summary"].split(". ")[0]  # 소수점이 아니라 문장 끝에서 자른다
    print("\n[토큰화 비교] ", sample)
    print("어절  :", tokenize_eojeol(sample))
    print("형태소:", tokenize_morph(sample))