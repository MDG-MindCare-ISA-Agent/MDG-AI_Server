import os
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
                    "사용자의 발화를 분석하여 다음 JSON 구조로만 응답하세요:\n"
                    "{\"primary\": \"감정\", \"confidence\": 0~1, \"triggers\": [\"단어1\", \"단어2\"]}"
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
    return json.loads(text_output)  # 모델이 준 JSON 문자열을 파싱