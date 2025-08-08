# services/simulation_service.py
import os
import re
import json
import requests
from typing import Dict, Optional
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# 환경 설정
# ─────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("CLOVA_API_KEY")
MODEL_ID = os.getenv("CLOVA_MODEL_ID_SIM", "HCX-005")
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

def _safe_parse_simulation(raw_text: str) -> Dict:
    print(f"[DEBUG] SimulationService text_output(raw): {raw_text!r}")
    raw_text = _strip_code_fences(raw_text)

    candidate = _extract_first_json_object(raw_text)
    print(f"[DEBUG] SimulationService extracted_json_before_cleanup: {candidate}")

    if not candidate:
        m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        candidate = m.group(0) if m else None
        print(f"[DEBUG] SimulationService regex_fallback_json: {candidate}")

    if not candidate:
        # 기본 더미 결과
        return {
            "cagr": 0.07,
            "max_dd": -0.2,
            "vol": 0.1,
            "equity_curve": [1.0, 1.01, 0.99, 1.02],
        }

    candidate = _remove_trailing_commas(candidate)
    print(f"[DEBUG] SimulationService json_str_before_loads: {candidate}")

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        print(f"[DEBUG] SimulationService json.loads error: {e}")
        parsed = {
            "cagr": 0.07,
            "max_dd": -0.2,
            "vol": 0.1,
            "equity_curve": [1.0, 1.01, 0.99, 1.02],
        }

    # 최소 키 보정
    parsed.setdefault("cagr", 0.07)
    parsed.setdefault("max_dd", -0.2)
    parsed.setdefault("vol", 0.1)
    parsed.setdefault("equity_curve", [1.0, 1.01, 0.99, 1.02])
    return parsed


# ─────────────────────────────────────────────────────────────
# 서비스
# ─────────────────────────────────────────────────────────────
class SimulationService:
    def run(self, strategy_data: Dict, horizon_months: int) -> Dict:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

        system_prompt = (
            "당신은 투자 시뮬레이션 전문가입니다.\n"
            "아래 JSON 한 개 객체만 출력하세요. 마지막 원소 뒤 콤마 금지, 문자열은 큰따옴표.\n"
            "{ \"cagr\": float, \"max_dd\": float, \"vol\": float, \"equity_curve\": [float] }"
        )

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"전략: {strategy_data}\n기간(개월): {horizon_months}"},
            ],
            "topP": 0.3,
            "topK": 0,
            "maxTokens": 512,
            "temperature": 0.2,
            "repetitionPenalty": 1.05,
            "stop": [],
            "seed": 0,
            "includeAiFilters": True,
        }

        res = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(3, 30))
        print(f"[DEBUG] SimulationService status_code: {res.status_code}")
        print(f"[DEBUG] SimulationService raw_response: {res.text}")

        if res.status_code == 400 and "model not found" in res.text:
            # 모델 ID 오류 → 더미로 폴백
            return {
                "cagr": 0.07,
                "max_dd": -0.2,
                "vol": 0.1,
                "equity_curve": [1.0, 1.01, 0.99, 1.02],
                "note": "모델 ID 오류로 더미 사용",
            }

        if res.status_code != 200:
            raise RuntimeError(f"API 호출 실패: {res.status_code} {res.text}")

        data = res.json()
        text_output = data["result"]["message"]["content"].strip()
        print(f"[DEBUG] SimulationService text_output(clean): {text_output!r}")

        parsed = _safe_parse_simulation(text_output)
        # 추가 메타 정보 포함(원한다면)
        parsed.setdefault("horizon_months", horizon_months)
        parsed.setdefault("applied_allocations", strategy_data.get("target_allocations", {}))
        parsed["message"] = (
            f"예상 지표(기간 {parsed['horizon_months']}개월): "
            f"CAGR {parsed['cagr']}, MaxDD {parsed['max_dd']}, Vol {parsed['vol']}"
        )
        return parsed


# step 호환용 래퍼
def run_simulation(strategy: Dict, horizon_months: int = 12) -> Dict:
    return SimulationService().run(strategy, horizon_months)