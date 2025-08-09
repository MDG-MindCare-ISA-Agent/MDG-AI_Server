# services/emotion_service.py
import os, re, json, uuid, textwrap, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("CLOVA_API_KEY")
MODEL = os.getenv("CLOVA_MODEL", "HCX-005")

# v3가 표준, 환경에 따라 testapp가 열려있는 경우도 있으니 폴백 엔드포인트 추가
ENDPOINTS = [
    f"https://clovastudio.stream.ntruss.com/v3/chat-completions/{MODEL}",
    f"https://clovastudio.stream.ntruss.com/testapp/v3/chat-completions/{MODEL}",
]

# ========== 공통 유틸 ==========

def _extract_json_object(text: str):
    """모델 출력에서 JSON 오브젝트 1개 안전 추출(비탐욕 정규식 → 슬라이스 보조)."""
    if not text:
        return None
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s:e+1])
        except Exception:
            pass
    return None

def _ensure_question(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return ""
    # 물음표 종결 보장
    if not q.endswith("?"):
        q = re.sub(r"[\.!\u3002\uFF01]+$", "", q).strip() + "?"
    # 예/아니오형 단순화 방지용(매우 기본적 가드)
    if re.fullmatch(r".*(네|아니오|맞아요|그렇나요)\??", q):
        q = "괜찮으시다면 지금 마음에 가장 남는 한 가지 순간을 떠올려보실 수 있을까요?"
    return q

def _post(messages, *, topP=0.7, temperature=0.4, maxTokens=256, timeout=(5, 30)):
    """Bearer v3 호출 + 간단 로그 + 엔드포인트 폴백."""
    if not API_KEY:
        print("[CLOVA] API_KEY missing")
        return None

    payload = {
        "messages": messages,
        "topP": topP, "topK": 0, "maxTokens": maxTokens, "temperature": temperature,
        "repetitionPenalty": 1.05, "stop": [], "seed": 0, "includeAiFilters": True
    }

    for url in ENDPOINTS:
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
            }
            res = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if res.status_code != 200:
                print(f"[CLOVA] {url} status={res.status_code} body={textwrap.shorten(res.text, 300)}")
                continue
            data = res.json()
            return (data.get("result", {}).get("message", {}).get("content") or "").strip()
        except Exception as e:
            print(f"[CLOVA] {url} error {type(e).__name__}: {e}")
            continue
    return None

# ========== Fallback들 ==========

def _fallback_emotion(user_text: str) -> dict:
    """네 기존 폴백 유지(통신 실패 시)."""
    t = (user_text or "").lower()
    emo = "info"; primary = "중립"
    if any(k in t for k in ["힘들", "떨어", "마이너스", "손실", "불안", "걱정"]):
        emo, primary = "emotion", "불안"
    elif any(k in t for k in ["분석", "위험", "가장", "문제", "워스트"]):
        emo, primary = "analysis", "중립"
    elif any(k in t for k in ["전략", "추천", "어떻게 할", "계획"]):
        emo, primary = "advice", "중립"
    empathy = "말씀만으로도 충분히 마음고생이 느껴져요. 같이 하나씩 정리해 볼게요."
    fq = _ensure_question("혹시 지금 가장 신경 쓰이는 종목/상황이 있나요")
    return {
        "type": emo,
        "primary": primary,
        "confidence": 0.6,
        "triggers": [],
        "empathy": empathy,
        "followup_question": fq,
        "message": f"{empathy} {fq}"
    }

def _fallback_empathy_and_question() -> dict:
    emp = "말씀 충분히 이해돼요. 요즘 마음이 많이 쓰이셨을 것 같아요."
    q = _ensure_question("괜찮으시다면 지금 가장 불편했던 지점을 한 가지만 말씀해 주실 수 있을까요")
    return {"empathy": emp, "question": q, "message": f"{emp} {q}"}

def _fallback_profile(user_text: str) -> dict:
    t = (user_text or "").lower()
    emo = "불안" if any(k in t for k in ["불안","걱정","손실","떨어","힘들"]) else "중립"
    tendency = "안정적" if any(k in t for k in ["해지","손절","원금","안전"]) else "중립적"
    return {"감정": emo, "성향": tendency}

# ========== (A) 공감 + 질문 텍스트 생성 ==========

def generate_empathy_and_question(user_text: str) -> dict:
    """
    반환 예:
    {
      "empathy": "공감 1문장",
      "question": "열린 질문 1문장",
      "message": "공감 1문장 질문 1문장(연결)"
    }
    """
    if not API_KEY:
        return _fallback_empathy_and_question()

    # 디벨롭된 프롬프트: 2문장(공감1+질문1), 마지막은 반드시 질문(물음표)로 끝
    system_prompt = (
        "당신은 투자자들의 감정과 재무 상황을 섬세하게 다루는 한국어 금융 심리 상담사입니다.\n"
        "아래 지침을 정확히 따르세요.\n"
        "— 톤: 따뜻하고 단정한 반존대, 비판/훈수 금지.\n"
        "— 형식: 한국어 정확히 2문장.\n"
        "— 구성: 1문장=정서적 공감(상대 감정/상황 반영), 2문장=열린 질문(탐색형).\n"
        "— 종결: 마지막 문장은 반드시 물음표('?')로 끝냄.\n"
        "— 질문: 예/아니오형·'왜?' 단독 금지, 직접적인 종목/비중 캐묻기 금지.\n"
        "— 길이: 문장별 25~80자.\n"
        "— 목적: 감정 정리와 자기표현을 돕는 부드러운 탐색.\n"
        "좋은 예) \"요즘 변동성이 커서 마음이 꽤 지치셨겠어요.\" \"괜찮으시다면 오늘 특히 마음이 무거워진 순간이 언제였는지 하나 떠올려보실 수 있을까요?\"\n"
    )
    user_prompt = (
        "다음 발화를 듣고 위 규칙대로 2문장(공감1+열린질문1)만 출력하세요. "
        "반드시 마지막 문장은 물음표로 끝냅니다.\n"
        f"발화: {user_text}"
    )

    out = _post(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user_prompt}],
        topP=0.8, temperature=0.7, maxTokens=120
    )
    if not out:
        return _fallback_empathy_and_question()

    # 2문장 분리 → 첫 문장은 공감, 두 번째는 질문
    parts = re.split(r'(?<=[\.\?\!])\s+', out.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) == 1:
        empathy = parts[0]
        question = "괜찮으시다면 지금 마음이 가장 흔들렸던 순간을 한 가지만 떠올려보실 수 있을까요?"
    else:
        empathy, question = parts[0], parts[1]

    question = _ensure_question(question)
    return {"empathy": empathy, "question": question, "message": f"{empathy} {question}"}

# ========== (B) 감정/성향 파싱(단일 입력) ==========

def parse_emotion_and_tendency(user_text: str) -> dict:
    """
    단일 문장을 근거로 감정/성향을 JSON으로 파싱.
    반환 예: {"감정": "불안", "성향": "안정적"}
    """
    if not API_KEY:
        return _fallback_profile(user_text)

    system_prompt = (
        "너는 사용자의 한 발화를 근거로 감정과 투자 성향을 간결히 추정하는 분석기다.\n"
        "- 감정: 핵심 1개(예: 불안/후회/혼란/기대/중립 등).\n"
        "- 성향: '안정적'/'중립적'/'공격적' 중 택1.\n"
        "- 출력은 JSON 오브젝트 1개만. 설명/문장/마크다운 금지."
    )
    user_prompt = (
        f"발화:\n{user_text}\n\n"
        "{\n"
        '  "감정": "<한 단어>",\n'
        '  "성향": "<안정적|중립적|공격적>"\n'
        "}"
    )
    out = _post(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user_prompt}],
        topP=1.0, temperature=0.0, maxTokens=120
    )
    obj = _extract_json_object(out) if out else None
    if not isinstance(obj, dict):
        return _fallback_profile(user_text)
    emo = str(obj.get("감정") or "중립")
    ten = str(obj.get("성향") or "중립적")
    if ten not in ("안정적", "중립적", "공격적"):
        ten = "중립적"
    return {"감정": emo, "성향": ten}

# ========== (C) 스키마 분류기 (마지막은 항상 질문으로 끝) ==========

def analyze_with_hyperclova(user_text: str) -> dict:
    """
    의도 스키마 JSON 강제.
    (followup_question은 열린 질문 1개, 반드시 물음표로 종결. 누락 시 생성기로 보충.)
    """
    if not API_KEY:
        return _fallback_emotion(user_text)

    system_prompt = (
        "당신은 금융 상담 전문가이자 감정 분석 챗봇입니다.\n\n"
        "사용자의 ‘중심 의도’를 먼저 판별하고, 아래 중 정확히 하나의 JSON 스키마로만 응답하세요.\n"
        "JSON만 출력(주석/설명/마크다운 금지), 모든 문자열은 큰따옴표.\n\n"
        "--- 공통 규칙 ---\n"
        "- empathy: 1~2문장, 따뜻하고 단정한 반존대.\n"
        "- followup_question: 열린 질문 1개, 예/아니오형 금지, '왜?' 단독 금지.\n"
        "- followup_question은 반드시 물음표('?')로 끝납니다.\n"
        "- JSON 문법 유효(마지막 콤마 금지).\n\n"
        "--- 스키마 ---\n"
        "1) 감정 표현 (Emotion)\n"
        "{\n"
        '  "type": "emotion",\n'
        '  "primary": "불안" | "기대" | "분노" | "중립" | "슬픔" | "기쁨",\n'
        '  "confidence": 0.0 ~ 1.0,\n'
        '  "triggers": ["키워드1", "키워드2"],\n'
        '  "empathy": "1~2문장 공감 멘트",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n\n"
        "2) 정보 탐색 (Info)\n"
        "{\n"
        '  "type": "info",\n'
        '  "summary": "요약",\n'
        '  "empathy": "1~2문장 공감 멘트(가능시)",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n\n"
        "3) 조언 요청 (Advice)\n"
        "{\n"
        '  "type": "advice",\n'
        '  "situation": "결정 요약",\n'
        '  "recommendation": "핵심 조언",\n'
        '  "empathy": "1~2문장 공감 멘트",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n\n"
        "4) 목표 설정 (Goal)\n"
        "{\n"
        '  "type": "goal",\n'
        '  "goal_summary": "목표 요약",\n'
        '  "time_frame": "기간(가능시)",\n'
        '  "empathy": "1~2문장 공감 멘트",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n\n"
        "5) 시스템 질문 (System)\n"
        "{\n"
        '  "type": "system",\n'
        '  "capabilities": ["감정 분석", "금융 용어 설명", "투자 전략 조언", "목표 기반 플래닝"],\n'
        '  "empathy": "1문장 공감 멘트(가능시)",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n\n"
        "6) 자산 분석 요청 (Analysis)\n"
        "{\n"
        '  "type": "analysis",\n'
        '  "intent": "분석 대상",\n'
        '  "required_info": ["현재 보유 종목", "비중", "투자 기간"],\n'
        '  "empathy": "1~2문장 공감 멘트",\n'
        '  "followup_question": "열린 질문(물음표로 종료)"\n'
        "}\n"
        "좋은 예: \"괜찮으시다면 지금 가장 마음이 쓰인 순간을 한 가지만 떠올려보실 수 있을까요?\"\n"
        "나쁜 예: 예/아니오 질문, '왜요?' 단독, '종목/비중을 지금 알려주세요' 직접 요구.\n"
    )

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "topP": 0.6, "topK": 0, "maxTokens": 320, "temperature": 0.2,
        "repetitionPenalty": 1.05, "stop": [], "seed": 0, "includeAiFilters": True
    }

    url = ENDPOINTS[0]
    rid = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": rid,
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=(5, 30))
        if res.status_code != 200:
            print(f"[CLOVA] analyze status={res.status_code} body={textwrap.shorten(res.text, 400)}")
            # 1차 실패 → 공감+질문 생성기로 대체
            g = generate_empathy_and_question(user_text)
            return {
                "type": "emotion", "primary": "중립", "confidence": 0.0,
                "empathy": g["empathy"], "followup_question": g["question"],
                "message": g["message"]
            }

        data = res.json()
        # 디버그용: 필터/원문 훑기 (콘솔에서 상황 파악)
        ai_filter = data.get("result", {}).get("aiFilter")
        content = (data.get("result", {}).get("message", {}).get("content") or "").strip()
        if ai_filter:
            print(f"[CLOVA] aiFilter={ai_filter}")
        if not content:
            print("[CLOVA] empty content → fallback to empathy generator")
            g = generate_empathy_and_question(user_text)
            return {
                "type": "emotion", "primary": "중립", "confidence": 0.0,
                "empathy": g["empathy"], "followup_question": g["question"],
                "message": g["message"]
            }

        # JSON 시도
        m = re.search(r"\{.*?\}", content, re.DOTALL)
        if not m:
            print(f"[CLOVA] no JSON found in content →\n---\n{content}\n---\n→ fallback to empathy generator")
            g = generate_empathy_and_question(user_text)
            return {
                "type": "emotion", "primary": "중립", "confidence": 0.0,
                "empathy": g["empathy"], "followup_question": g["question"],
                "message": g["message"]
            }

        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"[CLOVA] JSON decode error: {e}\ncontent(short)={textwrap.shorten(content, 400)}")
            g = generate_empathy_and_question(user_text)
            return {
                "type": "emotion", "primary": "중립", "confidence": 0.0,
                "empathy": g["empathy"], "followup_question": g["question"],
                "message": g["message"]
            }

        empathy = (obj.get("empathy") or "").strip()
        fq = _ensure_question(obj.get("followup_question") or "")
        if not fq:
            g = generate_empathy_and_question(user_text)
            if not empathy:
                empathy = g["empathy"]
            fq = _ensure_question(g["question"])

        obj["followup_question"] = fq
        obj["message"] = f"{empathy} {fq}".strip()
        obj.setdefault("type", "info")
        obj.setdefault("primary", "중립")
        return obj

    except Exception as e:
        print(f"[CLOVA] analyze error {type(e).__name__}: {e}")
        g = generate_empathy_and_question(user_text)
        return {
            "type": "emotion", "primary": "중립", "confidence": 0.0,
            "empathy": g["empathy"], "followup_question": g["question"],
            "message": g["message"]
        }