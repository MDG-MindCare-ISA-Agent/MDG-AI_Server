# services/profile_service.py
import json, os
from typing import Dict, Any, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_PATH = os.path.abspath(os.path.join(DATA_DIR, "persona_default.json"))

def _ensure_num(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def _calc_holding_metrics(h: Dict[str, Any]) -> Dict[str, Any]:
    qty = _ensure_num(h.get("quantity"))
    avg = _ensure_num(h.get("avg_price"))
    cur = _ensure_num(h.get("current_price"))
    invested = qty * avg
    value = qty * cur
    pnl_abs = value - invested
    pnl_pct = (pnl_abs / invested) if invested > 0 else 0.0
    out = dict(h)
    out.update({
        "amount_invested": invested,
        "current_value": value,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct
    })
    return out

def load_profile(user_id: str = "demo", path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """파일에서 페르소나 로드 + 파생지표 계산해서 반환."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"persona file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    # holdings 계산
    holdings = [_calc_holding_metrics(h) for h in profile.get("holdings", [])]
    total_value = sum(h["current_value"] for h in holdings)
    invested_total = sum(h["amount_invested"] for h in holdings)

    # 비중 계산
    for h in holdings:
        w = (h["current_value"] / total_value) * 100 if total_value > 0 else 0.0
        h["weight_pct"] = w

    profile["_computed"] = {
        "invested_total": invested_total,
        "market_value_total": total_value,
        "unrealized_pnl_abs": total_value - invested_total,
        "unrealized_pnl_pct": ((total_value - invested_total) / invested_total) if invested_total > 0 else 0.0
    }
    profile["holdings"] = holdings
    return profile

def portfolio_allocations(profile: Dict[str, Any]) -> Dict[str, float]:
    """파이프라인(step3/4)에서 쓰기 좋은 {ticker: weight(비율 0~1)} 반환."""
    holdings = profile.get("holdings", [])
    total_value = sum(h.get("current_value", 0.0) for h in holdings)
    if total_value <= 0:
        return {}
    allocs = {h["ticker"]: (h["current_value"] / total_value) for h in holdings}
    # 합 1.0 보정(미세 오차)
    s = sum(allocs.values())
    if s > 0:
        allocs = {k: v / s for k, v in allocs.items()}
    return allocs

def target_allocations(profile: Dict[str, Any]) -> Dict[str, float]:
    """타겟 비중 {ticker: 0~1} (없으면 빈 dict)."""
    d: Dict[str, float] = {}
    for h in profile.get("holdings", []):
        t = h.get("target_allocation_pct")
        if t is not None:
            d[h["ticker"]] = float(t) / 100.0
    # 합 1.0 보정
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s > 0 else d

def summarize(profile: Dict[str, Any]) -> str:
    """UI에 바로 뿌릴 수 있는 짧은 텍스트 요약."""
    c = profile.get("_computed", {})
    pnl_pct = c.get("unrealized_pnl_pct", 0.0) * 100
    lines = [
        f"{profile.get('name','사용자')}님의 포트폴리오 요약:",
        f"- 총 평가금액: {int(c.get('market_value_total', 0)):,} {profile.get('currency','KRW')}",
        f"- 누적 손익: {int(c.get('unrealized_pnl_abs', 0)):,} ({pnl_pct:.1f}%)",
        "- 현재 비중(상위):"
    ]
    # 상위 3개 by weight
    tops = sorted(profile.get("holdings", []), key=lambda x: x.get("weight_pct", 0.0), reverse=True)[:3]
    for h in tops:
        lines.append(f"  · {h['ticker']} {h['weight_pct']:.1f}% (평단 {int(h['avg_price']):,} → 현재 {int(h['current_price']):,})")
    return "\n".join(lines)

def save_profile(profile: Dict[str, Any], path: str = DEFAULT_PATH) -> None:
    """계산필드 제거 후 저장(원본 구조 유지)."""
    p = dict(profile)
    p.pop("_computed", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)