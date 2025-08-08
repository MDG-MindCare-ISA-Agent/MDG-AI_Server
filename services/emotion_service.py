import os, re, json, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("CLOVA_API_KEY")
ENDPOINT = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005"

def _fallback_emotion(user_text: str) -> dict:
    """CLOVA 키/네트워크가 없을 때 간단 규칙 기반."""
    t = user_text.lower()
    emo = "info"
    primary = "중립"
    if any(k in t for k in ["힘들", "떨어", "마이너스", "손실", "불안", "걱정"]):
        emo, primary = "emotion", "불안"
    elif any(k in t for k in ["분석", "위험", "가장", "문제", "워스트"]):
        emo, primary = "analysis", "중립"
    elif any(k in t for k in ["전략", "추천", "어떻게 할", "계획"]):
        emo, primary = "advice", "중립"
    empathy = "말씀만으로도 충분히 마음고생이 느껴져요. 같이 하나씩 정리해 볼게요."
    fq = "혹시 지금 가장 신경 쓰이는 종목/상황이 있나요?"
    return {
        "type": emo,
        "primary": primary,
        "confidence": 0.6,
        "triggers": [],
        "empathy": empathy,
        "followup_question": fq,
        "message": empathy
    }

def analyze_with_hyperclova(user_text: str) -> dict:
    if not API_KEY:
        return _fallback_emotion(user_text)

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
        "topP": 0.7, "topK": 0, "maxTokens": 256, "temperature": 0.4,
        "repetitionPenalty": 1.05, "stop": [], "seed": 0, "includeAiFilters": True
    }
    try:
        res = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(5, 30))
        if res.status_code != 200:
            return _fallback_emotion(user_text)
        text_output = res.json()["result"]["message"]["content"].strip()
        m = re.search(r"\{.*\}", text_output, re.DOTALL)
        if not m:
            return _fallback_emotion(user_text)
        obj = json.loads(m.group(0))
        obj.setdefault("empathy", "")
        obj["message"] = obj.get("empathy") or ""
        return obj
    except Exception:
        return _fallback_emotion(user_text)