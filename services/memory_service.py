# services/memory_service.py
import uuid
from typing import Dict, Any, List
from pprint import pprint

# 인메모리 저장 (프로덕션은 Redis/DB 권장)
_CONVOS: Dict[str, List[Dict[str, Any]]] = {}
_STATE: Dict[str, Dict[str, Any]] = {}  # 마지막 선택지 등

def get_convo_id(session) -> str:
    cid = session.get("cid")
    if not cid:
        cid = str(uuid.uuid4())
        session["cid"] = cid
    return cid

def load_history(convo_id: str) -> List[Dict[str, Any]]:
    return _CONVOS.get(convo_id, [])

# get_history 별칭(혹시 기존 코드에서 이 이름을 쓰는 곳 대비)
get_history = load_history

def save_turn(convo_id: str, user_input: Dict[str, Any], model_output: Dict[str, Any]) -> None:
    _CONVOS.setdefault(convo_id, [])
    _CONVOS[convo_id].append({"user": user_input, "assistant": model_output})
    # 길이 제한
    if len(_CONVOS[convo_id]) > 30:
        _CONVOS[convo_id] = _CONVOS[convo_id][-30:]

    # 디버그 로그
    print(f"\n🗂️ [HISTORY] convo_id={convo_id} (총 {len(_CONVOS[convo_id])}턴)")
    pprint(_CONVOS[convo_id][-1])
    print("-" * 60)

def reset_memory(convo_id: str):
    _CONVOS[convo_id] = []
    _STATE.pop(convo_id, None)
    print(f"♻️ 메모리 초기화: {convo_id}")

def summarize_history_for_prompt(hist: List[Dict[str, Any]]) -> str:
    if not hist: 
        return ""
    last = hist[-3:]
    items = []
    for turn in last:
        u = turn.get("user", {})
        a = turn.get("assistant", {})
        items.append(f"Q:{u.get('text','')} | Pick:{u.get('pick','')} | A-head:{(a.get('message') or '')[:40]}")
    return " | ".join(items)

# 마지막 선택지 보관/조회 — “1번해줘” 해석에 쓰임
def set_last_options(convo_id: str, options: List[Dict[str, Any]]):
    _STATE.setdefault(convo_id, {})
    _STATE[convo_id]["last_options"] = options or []
    print(f"✅ [CHOICES SAVED] {convo_id} -> {options}")

def get_last_options(convo_id: str) -> List[Dict[str, Any]]:
    return _STATE.get(convo_id, {}).get("last_options", [])


def set_awaiting_choice(convo_id: str, options: List[Dict[str, Any]]):
    _STATE.setdefault(convo_id, {})
    _STATE[convo_id]["awaiting_choice"] = True
    _STATE[convo_id]["last_options"] = options or []

def clear_awaiting_choice(convo_id: str):
    if convo_id in _STATE:
        _STATE[convo_id]["awaiting_choice"] = False

def is_awaiting_choice(convo_id: str) -> bool:
    return bool(_STATE.get(convo_id, {}).get("awaiting_choice"))