"""공개용 데이터 만들기

news.json에서 기사 본문(body)만 빼고 data/news_public.json으로 저장한다.
기사 본문은 언론사 저작물이라 GitHub에 올리지 않는다.
제목, 링크, 그리고 내가 직접 쓴 기준 요약은 남긴다.
"""
import json
import os

with open("news.json", encoding="utf-8") as f:
    articles = json.load(f)

public = [{k: v for k, v in a.items() if k != "body"} for a in articles]

os.makedirs("data", exist_ok=True)
with open("data/news_public.json", "w", encoding="utf-8") as f:
    json.dump(public, f, ensure_ascii=False, indent=2)

print(f"data/news_public.json 저장 완료 (기사 {len(public)}개, 본문 제외)")
