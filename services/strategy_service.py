from typing import List, Dict, Any

def _normalize_allocations(ta: Dict[str, Any]) -> Dict[str, float]:
    if not ta: return {}
    # 문자열/정수 섞여도 float으로, 0~100 들어오면 0~1로 보정
    ta = {k: float(v) for k, v in ta.items()}
    if max(ta.values()) > 1.0:
        ta = {k: v/100.0 for k, v in ta.items()}
    s = sum(ta.values()) or 1.0
    return {k: v/s for k, v in ta.items()}

def normalize_candidates(raw_list: Any) -> List[Dict[str, Any]]:
    """외부 함수가 생성해서 넘어온 후보 목록을 표준화."""
    out: List[Dict[str, Any]] = []
    if not isinstance(raw_list, list):
        return out
    for i, s in enumerate(raw_list, start=1):
        if not isinstance(s, dict): 
            continue
        out.append({
            "id": s.get("id") or f"S{i}",
            "label": s.get("label") or f"전략 {i}",
            "rationale": s.get("rationale") or "",
            "target_allocations": _normalize_allocations(s.get("target_allocations") or {}),
        })
    return out

# 여기서는 '생성'을 하지 않습니다. (외부에서 만들어서 넣어주세요)