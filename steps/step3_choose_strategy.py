# steps/step3_choose_strategy.py
from routing import needs_strategy, needs_portfolio_qa
from services.strategy_service import recommend_strategy_many, recommend_strategy

def _calc_positions(ctx):
    pf = (ctx.get("profile") or {}).get("holdings") or []
    out = []
    for h in pf:
        ret = float(h.get("pnl_pct") or 0.0)   # profile_service에서 계산해 둔 값(-0.25 = -25%)
        out.append({
            "ticker": h.get("ticker"),
            "weight_pct": float(h.get("weight_pct") or 0.0),  # 0~100
            "return_pct": ret * 100.0,
            "pnl_abs": float(h.get("pnl_abs") or 0.0),
        })
    return out

def _answer_portfolio_qa(ctx):
    pos = _calc_positions(ctx)
    emo = ctx.get("emotion") or {}
    lines = []
    if emo.get("empathy"):
        lines.append(emo["empathy"])

    if not pos:
        lines.append("보유 종목 데이터가 부족해요. (티커/수량/평단/현재가가 있으면 정확히 짚어드릴게요.)")
    else:
        worst = min(pos, key=lambda x: x.get("return_pct", 0.0))
        lines.append(f"가장 리스크가 커 보이는 종목은 **{worst['ticker']}** 입니다.")
        lines.append(f"- 평가손익률: {worst['return_pct']:.1f}%")
        lines.append(f"- 포트폴리오 비중: {worst['weight_pct']:.1f}%")
        lines.append("선택지: ① 비중 축소 ② 손절/트레일링 스탑 ③ 헷지(상관관계/옵션) ④ 장기 보유 전제면 분할매수만 고려")
        lines.append("원하시면 이 종목만 시뮬레이션으로 리스크-리턴을 가볍게 체크해볼까요? (?simulate=true)")

    ctx["portfolio_answer"] = "\n".join(lines)
    ctx["strategy"] = None  # 이번 턴은 전략 호출 안 함
    return ctx

def choose_strategy(ctx):
    # 포트폴리오 Q&A 우선
    if needs_portfolio_qa(ctx):
        return _answer_portfolio_qa(ctx)

    if not needs_strategy(ctx):
        ctx["strategies"] = []          # 후보들 저장
        ctx["strategy"] = None
        return ctx

    emotion = ctx.get("emotion")
    portfolio = ctx.get("input", {}).get("portfolio", {})
    pick = (ctx.get("input", {}) or {}).get("pick")  # "1" 또는 "S2"

    # 1) 후보 2~3개 제안
    strategies = recommend_strategy_many(emotion, portfolio, top_n=3)
    ctx["strategies"] = strategies

    # 2) 사용자가 선택했으면 확정
    if pick:
        chosen = None
        for i, s in enumerate(strategies, start=1):
            if str(pick) in (str(i), s.get("id")):
                chosen = s; break
        ctx["strategy"] = chosen
        return ctx

    # 3) 아직 선택 전 → 확정 전략 없음
    ctx["strategy"] = None
    return ctx