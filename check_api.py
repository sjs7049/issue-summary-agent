"""1단계: Gemini API 연결 확인

1) .env 파일에서 API 키를 읽는다.
2) 내 키로 쓸 수 있는 모델 목록을 출력한다.
3) 그중 하나로 짧은 질문을 보내 답이 오는지 확인한다.
"""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()  # 같은 폴더의 .env 파일을 읽어 환경변수로 등록

if not os.getenv("GEMINI_API_KEY"):
    raise SystemExit(".env 파일에 GEMINI_API_KEY가 없습니다. .env.example을 참고하세요.")

client = genai.Client()  # GEMINI_API_KEY 환경변수를 자동으로 사용

# 1) 쓸 수 있는 모델 이름 확인 (이름에 flash가 들어간 것만)
print("[사용 가능한 flash 모델]")
for model in client.models.list():
    if "flash" in model.name:
        print(" -", model.name)

# 2) 위 목록에서 고른 모델 이름을 여기에 넣는다 ("models/" 앞부분은 빼고)
MODEL = "gemini-3.5-flash"

interaction = client.interactions.create(
    model=MODEL,
    input="한 문장으로 자기소개를 해줘.",
)
print("\n[모델 응답]")
print(interaction.output_text)
