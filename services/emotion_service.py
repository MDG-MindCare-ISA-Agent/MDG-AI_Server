import os
import re
import json
import requests
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

API_KEY = os.getenv("CLOVA_API_KEY")
if not API_KEY:
    raise RuntimeError("환경변수 CLOVA_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

ENDPOINT = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005"

def analyze_with_hyperclova(user_text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    payload = {
        "messages": [
            {
              "role": "system",
              "content": (
                  "당신은 금융 상담 전문가입니다.\n"
                  "사용자의 발화를 분석하여 반드시 JSON 형식으로만 응답하세요.\n"
                  "JSON 외의 설명, 텍스트는 절대 포함하지 마세요.\n"
                  "출력 예시: {\"primary\": \"감정\", \"confidence\": 0.85, \"triggers\": [\"단어1\", \"단어2\"]}"
              )
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": 256,
        "temperature": 0.5,
        "repetitionPenalty": 1.1,
        "stop": [],
        "seed": 0,
        "includeAiFilters": True
    }

    res = requests.post(ENDPOINT, headers=headers, json=payload)
    if res.status_code != 200:
        raise RuntimeError(f"API 호출 실패: {res.status_code} {res.text}")

    data = res.json()

    text_output = data["result"]["message"]["content"].strip()

    # JSON 구조만 뽑기 (중괄호부터 끝까지)
    match = re.search(r"\{.*\}", text_output, re.DOTALL)
    if not match:
        raise RuntimeError(f"모델 응답에 JSON이 없습니다: {text_output}")

    json_str = match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 파싱 실패: {e} / 원본: {json_str}")