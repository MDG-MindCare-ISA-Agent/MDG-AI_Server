# services/strategy_service.py
import os
import re
import json
import requests
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# 환경 설정
# ─────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("CLOVA_API_KEY")
MODEL_ID = os.getenv("CLOVA_MODEL_ID_STRATEGY", "HCX-005")
ENDPOINT = f"https://clovastudio.stream.ntruss.com/v3/chat-completions/{MODEL_ID}"

if not API_KEY:
    raise RuntimeError("CLOVA_API_KEY 가 설정되지 않았습니다 (.env 확인).")

# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def _strip_code_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)

def _extract_first_json_object(text: str) -> Optional[str]:
    start = None
    depth = 0
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start:i+1]
    return None

def _safe_parse_strategy(raw_text: str, portfolio: Dict[str, float]) -> Dict[str, Any]:
    raw_text = _strip_code_fences(raw_text)
    candidate = _extract_first_json_object(raw_text)
    if not candidate:
        m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        candidate = m.group(0) if m else None
    if not candidate:
        return {
            "label": "기본 전략",
            "rationale": "JSON 블록을 찾지 못해 기본 전략 사용",
            "target_allocations": portfolio or {}
        }
    candidate = _remove_trailing_commas(candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        return {
            "label": "기본 전략",
            "rationale": f"파싱 오류로 기본 전략 사용: {str(e)}",
            "target_allocations": portfolio or {}
        }

def _normalize_allocations(ta: Dict[str, Any]) -> Dict[str, float]:
    if not ta:
        return {}
    # 문자열/정수 섞여도 float으로
    ta = {k: float(v) for k, v in ta.items()}
    # 0~100이면 0~1로 변환
    if ta and max(ta.values()) > 1.0:
        ta = {k: v / 100.0 for k, v in ta.items()}
    s = sum(ta.values()) or 1.0
    return {k: v / s for k, v in ta.items()}

def _extract_first_json(text: str) -> Optional[str]:
    text = _remove_trailing_commas(_strip_code_fences(text)).strip()
    if text.startswith("["):
        depth = 0; start = None
        for i, ch in enumerate(text):
            if ch == "[":
                if depth == 0: start = i
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start:i+1]
    # 객체 하나라도
    depth = 0; start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i+1]
    return None

# ─────────────────────────────────────────────────────────────
# 서비스
# ─────────────────────────────────────────────────────────────
class StrategyService:
    def recommend(self, emotion_data: dict, portfolio: Dict[str, float]) -> Dict[str, Any]:
        """전략 1개 추천"""
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        system_prompt = (
            "당신은 금융 전략 추천 전문가입니다.\n"
            "감정 분석 결과와 포트폴리오를 바탕으로 투자 전략을 제시하세요.\n"
            "응답은 반드시 유효한 JSON **한 개 객체**만 출력하세요. "
            "모든 문자열은 큰따옴표(\")로 감싸고, 마지막 원소 뒤 콤마 금지.\n"
            "{\n"
            "  \"label\": \"전략 이름\",\n"
            "  \"rationale\": \"전략 근거\",\n"
            "  \"target_allocations\": {\"티커\": 비율}\n"
            "}\n"
        )
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"감정 분석: {emotion_data}\n포트폴리오: {portfolio}"},
            ],
            "topP": 0.3, "topK": 0, "maxTokens": 256, "temperature": 0.2,
            "repetitionPenalty": 1.05, "stop": [], "seed": 0, "includeAiFilters": True,
        }
        res = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(3, 30))
        if res.status_code == 400 and "model not found" in res.text:
            return {
                "label": "기본 전략",
                "rationale": "모델 ID 오류로 기본 전략 사용",
                "target_allocations": portfolio or {},
            }
        if res.status_code != 200:
            raise RuntimeError(f"API 호출 실패: {res.status_code} {res.text}")

        text_output = res.json()["result"]["message"]["content"].strip()
        parsed = _safe_parse_strategy(text_output, portfolio)
        parsed.setdefault("label", "전략")
        parsed.setdefault("rationale", "")
        parsed["target_allocations"] = _normalize_allocations(parsed.get("target_allocations") or portfolio or {})
        parsed["message"] = f"추천 전략은 **{parsed['label']}** 입니다.\n근거: {parsed['rationale']}".strip()
        return parsed

    def recommend_many(self, emotion_data: dict, portfolio: Dict[str, float], top_n: int = 3) -> List[Dict[str, Any]]:
        """전략 N개 추천"""
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        system_prompt = (
            "당신은 금융 전략 추천 전문가입니다.\n"
            f"감정 분석과 포트폴리오를 바탕으로 서로 다른 전략 {top_n}개를 제시하세요.\n"
            "JSON 배열만 출력(마크다운/설명 금지). 마지막 콤마 금지.\n"
            "{ \"id\": \"S1\", \"label\": \"전략 이름\", \"rationale\": \"근거(1~2문장)\", "
            "\"target_allocations\": {\"티커\": 비율(0~1 또는 0~100)} }\n"
        )
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"감정 분석: {emotion_data}\n포트폴리오: {portfolio}"},
            ],
            "topP": 0.3, "topK": 0, "maxTokens": 640, "temperature": 0.2,
            "repetitionPenalty": 1.05, "stop": [], "seed": 0, "includeAiFilters": True,
        }
        res = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(3, 30))
        if res.status_code != 200:
            return [{
                "id": "S1",
                "label": "기본 전략",
                "rationale": "API 응답 오류로 기본 전략 사용",
                "target_allocations": _normalize_allocations(portfolio),
                "message": "추천 전략은 **기본 전략** 입니다."
            }]

        text = res.json()["result"]["message"]["content"]
        raw = _extract_first_json(text) or "[]"
        try:
            arr = json.loads(raw)
            if isinstance(arr, dict):
                arr = [arr]
        except Exception:
            arr = []

        out: List[Dict[str, Any]] = []
        for i, s in enumerate(arr[:top_n], start=1):
            ta = _normalize_allocations((s or {}).get("target_allocations") or {})
            label = (s or {}).get("label") or f"전략 {i}"
            rationale = (s or {}).get("rationale") or ""
            out.append({
                "id": (s or {}).get("id") or f"S{i}",
                "label": label,
                "rationale": rationale,
                "target_allocations": ta,
                "message": f"추천 전략은 **{label}** 입니다.\n근거: {rationale}".strip()
            })

        if not out:
            out = [{
                "id": "S1",
                "label": "기본 전략",
                "rationale": "모델 응답 파싱 실패로 기본 전략 사용",
                "target_allocations": _normalize_allocations(portfolio),
                "message": "추천 전략은 **기본 전략** 입니다."
            }]
        return out

# 모듈 레벨 래퍼
def recommend_strategy(emotion_data: dict, portfolio: Dict[str, float]) -> Dict[str, Any]:
    return StrategyService().recommend(emotion_data, portfolio)

def recommend_strategy_many(emotion_data: dict, portfolio: Dict[str, float], top_n: int = 3):
    return StrategyService().recommend_many(emotion_data, portfolio, top_n)