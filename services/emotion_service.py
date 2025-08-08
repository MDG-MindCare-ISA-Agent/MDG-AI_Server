# services/emotion_service.py (analyze_with_hyperclova)
import os, re, json, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("CLOVA_API_KEY")
ENDPOINT = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005"

def analyze_with_hyperclova(user_text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    system_prompt = (
        "당신은 금융 상담 전문가이자 감정 분석 챗봇입니다.\n\n"
        "사용자의 ‘중심 의도’를 먼저 판별하고, 아래 중 정확히 하나의 JSON 스키마로만 응답하세요.\n"
        "JSON만 출력하고, 주석/설명/마크다운 금지. 모든 문자열은 큰따옴표로 감싸세요.\n\n"
        "--- 공통 규칙 ---\n"
        "- 가능한 경우 공감 멘트(empathy)를 2~3문장으로 생성하세요.\n"
        "- followup_question은 실제 대화 연속을 위한 열린 질문 1개만 주세요.\n"
        "- JSON은 유효한 문법을 유지하세요(마지막 콤마 금지).\n\n"
        "--- 스키마 ---\n"
        "1) 감정 표현 (Emotion)\n"
        "{\n"
        "  \"type\": \"emotion\",\n"
        "  \"primary\": \"불안\" | \"기대\" | \"분노\" | \"중립\" | \"슬픔\" | \"기쁨\",\n"
        "  \"confidence\": 0.0 ~ 1.0,\n"
        "  \"triggers\": [\"키워드1\", \"키워드2\"],\n"
        "  \"empathy\": \"1~2문장 공감 멘트\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n\n"
        "2) 정보 탐색 (Info)\n"
        "{\n"
        "  \"type\": \"info\",\n"
        "  \"summary\": \"요약\",\n"
        "  \"empathy\": \"1~2문장 공감 멘트(가능시)\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n\n"
        "3) 조언 요청 (Advice)\n"
        "{\n"
        "  \"type\": \"advice\",\n"
        "  \"situation\": \"결정 요약\",\n"
        "  \"recommendation\": \"핵심 조언\",\n"
        "  \"empathy\": \"1~2문장 공감 멘트\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n\n"
        "4) 목표 설정 (Goal)\n"
        "{\n"
        "  \"type\": \"goal\",\n"
        "  \"goal_summary\": \"목표 요약\",\n"
        "  \"time_frame\": \"기간(가능시)\",\n"
        "  \"empathy\": \"1~2문장 공감 멘트\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n\n"
        "5) 시스템 질문 (System)\n"
        "{\n"
        "  \"type\": \"system\",\n"
        "  \"capabilities\": [\"감정 분석\", \"금융 용어 설명\", \"투자 전략 조언\", \"목표 기반 플래닝\"],\n"
        "  \"empathy\": \"1문장 공감 멘트(가능시)\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n\n"
        "6) 자산 분석 요청 (Analysis)\n"
        "{\n"
        "  \"type\": \"analysis\",\n"
        "  \"intent\": \"분석 대상\",\n"
        "  \"required_info\": [\"현재 보유 종목\", \"비중\", \"투자 기간\"],\n"
        "  \"empathy\": \"1~2문장 공감 멘트\",\n"
        "  \"followup_question\": \"후속 질문\"\n"
        "}\n"
    )

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
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

    m = re.search(r"\{.*\}", text_output, re.DOTALL)
    if not m:
        raise RuntimeError(f"모델 응답에 JSON이 없습니다: {text_output}")

    json_str = m.group(0)
    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 파싱 실패: {e} / 원본: {json_str}")

    # 안전 보정: type 누락 시 info로
    if "type" not in obj:
        obj["type"] = "info"
    # empathy 누락 시 빈 문자열
    # services/emotion_service.py (리턴 직전)
    obj.setdefault("empathy", "")
    obj["message"] = obj.get("empathy") or ""  # 혹은 좀 더 다듬은 한두 문장
    return obj