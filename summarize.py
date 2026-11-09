"""3단계: 이슈 요약 노드

news.json의 기사마다 Gemini로 요약을 만들고 summaries.json에 저장한다.
summarize() 함수는 5단계 피드백 루프에서 다시 불러 쓴다.
"""
import json
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()
# 응답이 60초 넘게 안 오면 기다리지 않고 에러를 낸다 (단위: 밀리초)
client = genai.Client(http_options={"timeout": 60_000})

# 3.6 이상은 temperature를 무시해서 3.5 계열을 쓴다.
# gemini-3.5-flash의 무료 할당량을 다 써서, 할당량이 따로 잡히는 lite 모델로 바꿨다.
MODEL = "gemini-3.5-flash-lite"
MAX_CHARS = 400

# 제안서의 "프롬프트로 출력 형식 고정"에 해당하는 부분
SYSTEM_INSTRUCTION = f"""너는 증권사 앱에서 급등락 종목의 원인을 브리핑하는 요약가다.
기사만 근거로 요약하고, 기사에 없는 내용은 절대 추가하지 않는다.

출력 규칙:
1. 첫 문장은 종목명으로 시작하고, 등락률과 주가를 쓴다.
2. 이어서 주가가 움직인 원인을 기사에 나온 근거와 함께 쓴다.
3. 기사에 반대 의견이나 주의할 점이 있으면 마지막 문장에 쓴다.
4. 200자 이상 {MAX_CHARS}자 이하의 한 문단으로 쓴다. 제목, 목록, 따옴표 강조는 쓰지 않는다.
5. 투자 권유나 전망을 직접 하지 않는다.
6. 모든 문장은 '~했다', '~이다'처럼 신문 기사체 평서문으로 끝낸다. '~습니다'는 쓰지 않는다."""


def summarize(article, temperature=0.2, extra_instruction=""):
    """기사 하나를 요약해 문자열로 돌려준다.

    temperature: 낮을수록 매번 비슷한 답, 높을수록 다양한 답
    extra_instruction: 재시도할 때 덧붙일 지시 (5단계에서 사용)
    """
    prompt = (
        f"종목: {article['stock']}\n"
        f"등락률: {article['change_rate']}\n"
        f"기사 제목: {article['title']}\n"
        f"기사 본문: {article['body']}\n"
    )
    if extra_instruction:
        prompt += f"\n추가 지시: {extra_instruction}\n"

    # 무료 등급은 분당 요청 수 제한이 있다. 막히면 기다렸다가 최대 3번까지 다시 보낸다.
    for attempt in range(1, 4):
        try:
            interaction = client.interactions.create(
                model=MODEL,
                system_instruction=SYSTEM_INSTRUCTION,
                input=prompt,
                generation_config={"temperature": temperature},
            )
            return interaction.output_text.strip()
        except Exception as e:  # 시간 초과, 요청 제한(429) 등
            wait = 30 * attempt
            print(f"  API 호출 실패({attempt}/3): {type(e).__name__}: {str(e)[:120]}", flush=True)
            if attempt == 3:
                raise
            print(f"  {wait}초 기다렸다가 다시 시도합니다...", flush=True)
            time.sleep(wait)


if __name__ == "__main__":
    with open("news.json", encoding="utf-8") as f:
        articles = json.load(f)

    results = []
    for a in articles:
        summary = summarize(a)
        length_ok = len(summary) <= MAX_CHARS
        results.append({"id": a["id"], "stock": a["stock"], "summary": summary, "length": len(summary)})

        print(f"[{a['id']}] {a['stock']} ({len(summary)}자, 길이 {'OK' if length_ok else '초과'})")
        print(summary, "\n")
        time.sleep(2)  # 무료 등급의 분당 요청 제한에 걸리지 않도록 잠깐 쉰다

    with open("summaries.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("summaries.json에 저장했습니다.")