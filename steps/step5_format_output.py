# steps/step5_format_output.py (format_output 내부 일부만 확장)
def _norm_allocs(allocs: dict):
    if not allocs: return {}
    s = sum(allocs.values()) or 1.0
    return {k: round(100.0*float(v)/s, 1) for k, v in allocs.items()}

def format_output(ctx):
    plan = ctx.get("_plan") or {}
    parts = []

    emo = ctx.get("emotion") or {}
    if emo.get("message"):
        parts.append(emo["message"])

    # ✅ 포트폴리오 Q&A가 있으면 최우선
    if ctx.get("portfolio_answer"):
        parts.append(ctx["portfolio_answer"])
    else:
        # NEW: 전략 후보 안내 (아직 선택 안 됐을 때)
        strategies = ctx.get("strategies") or []
        chosen = ctx.get("strategy") or None
        if strategies and not chosen:
            parts.append("전략 후보를 제안드려요. 원하시는 번호/ID로 선택해 주세요:")
            for i, s in enumerate(strategies, start=1):
                allocs = _norm_allocs(s.get("target_allocations") or {})
                alloc_str = ", ".join([f"{k} {v:.1f}%" for k,v in allocs.items()])
                parts.append(
                    f"{i}. **{s.get('label','전략')}** — {s.get('rationale','')}\n"
                    f"   · 비중: {alloc_str}"
                )
            parts.append("예: `?pick=1` 로 선택. 시뮬까지 보려면 `?pick=1&simulate=true`")

        # 선택된 전략 출력
        if chosen:
            allocs = _norm_allocs(chosen.get("target_allocations") or {})
            parts.append(f"선택하신 전략은 **{chosen.get('label','전략')}** 입니다.")
            if chosen.get("rationale"):
                parts.append(f"근거: {chosen['rationale']}")
            if allocs:
                parts.append("제안 비중: " + ", ".join([f"{k} {v:.1f}%" for k,v in allocs.items()]))

        # info/strategy/sim 기존 출력 유지
        if plan.get("info"):
            info = ctx.get("info") or {}
            if info.get("message"):
                parts.append(info["message"])
            elif info.get("summary"):
                parts.append(info["summary"])

        if plan.get("strategy") and not chosen:
            parts.append("원하시면 번호로 선택해 주세요. (?pick=1)")

        if plan.get("simulation") and ctx.get("simulation"):
            sm = ctx["simulation"]
            if sm.get("message"):
                parts.append(sm["message"])

    ans = "\n\n".join([p for p in parts if p])
    ctx["output"] = {
        "emotion": ctx.get("emotion"),
        "info": ctx.get("info"),
        "strategies": ctx.get("strategies"),   # ← NEW
        "strategy": ctx.get("strategy"),
        "simulation": ctx.get("simulation"),
        "_meta": ctx.get("_meta", {}),
        "answer": ans,
        "message": ans,
        "ok": True,
    }
    return ctx