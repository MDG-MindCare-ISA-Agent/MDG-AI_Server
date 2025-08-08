# steps/step3_choose_strategy.py
from typing import List, Dict, Any
from routing import needs_strategy, needs_portfolio_qa
from services.profile_service import load_profile
from services.strategy_service import normalize_candidates
from services.memory_service import set_awaiting_choice, clear_awaiting_choice

def _calc_positions(ctx):
    pf = (ctx.get("profile") or {}).get("holdings") or []
    out = []
    for h in pf:
        ret = float(h.get("pnl_pct") or 0.0)   # -0.25 = -25%
        out.append({
            "ticker": h.get("ticker"),
            "weight_pct": float(h.get("weight_pct") or 0.0),  # 0~100
            "return_pct": ret * 100.0,
            "pnl_abs": float(h.get("pnl_abs") or 0.0),
        })
    return out

def _answer_portfolio_qa(ctx):
    pos = _calc_positions(ctx)  # 프로필 기반
    if not pos:
        ctx["portfolio_answer"] = (
            "보유 종목 데이터가 부족해요. (티커/수량/평단/현재가가 있으면 정확히 짚어드릴게요.)"
        )
        ctx["strategy"] = None
        return ctx

    # 1) 기본 분석
    worst = min(pos, key=lambda x: x.get("return_pct", 0.0))
    worst_ticker = worst['ticker']
    worst_ret = worst['return_pct']
    worst_w = worst['weight_pct']

    # 2) 선택지 세팅 (이게 메모리에 저장될 재료)
    choices = [
        {"id": "1", "label": "비중 축소", "ticker": worst_ticker},
        {"id": "2", "label": "손절/트레일링 스탑", "ticker": worst_ticker},
        {"id": "3", "label": "헷지(상관/옵션)", "ticker": worst_ticker},
        {"id": "4", "label": "분할매수(장기 전제)", "ticker": worst_ticker},
    ]
    ctx["choices"] = choices  # <-- 중요: step5에서 _choices로 실려 나가고 pipeline이 저장함

    convo_id = (ctx.get("_meta") or {}).get("convo_id")
    if convo_id:
        # ✅ 선택지 보여줬으면 "선택 대기 모드" 켜기
        set_awaiting_choice(convo_id, choices)


    # 3) 사용자가 이번 턴에 pick 했는지 처리
    pick = (ctx.get("input") or {}).get("pick")
    if pick:
        # id 매칭
        picked = next((c for c in choices if c["id"] == str(pick)), None)
        if picked:
            action = picked["label"]
            tkr = picked["ticker"]
            # 여기서 실제 로직 분기 (데모용 문장)
            if pick == "1":
                plan = (
                    f"[실행안: {tkr} 비중 축소]\n"
                    f"- 현재 비중 {worst_w:.1f}% → 목표 20%로 낮추기(예시)\n"
                    "- 체계: 2~3회 분할 매도, 반등 시 재진입 규칙 명시\n"
                    "- 리스크: 추세 반전 놓칠 수 있음 → 재진입 트리거 설정\n"
                )
            elif pick == "2":
                plan = (
                    f"[실행안: {tkr} 손절/트레일링]\n"
                    "- 손절선: 최근 저점 하향 이탈 시 전량/절반 정리\n"
                    "- 트레일링: 고점 대비 -7~10% 하락 시 매도\n"
                    "- 리스크: 노이즈로 인한 빈번한 체결 → 변동성 고려\n"
                )
            elif pick == "3":
                plan = (
                    f"[실행안: {tkr} 헷지]\n"
                    "- 상쇄 ETF/인버스 일부 편입 또는 옵션 보호(예: 풋)\n"
                    "- 상관 높은 종목/섹터로 상쇄 포지션\n"
                    "- 리스크: 헷지 비용 발생, 과도한 상쇄는 수익 희석\n"
                )
            elif pick == "4":
                plan = (
                    f"[실행안: {tkr} 분할매수]\n"
                    "- 전제: 장기 보유 의사+기초 펀더멘탈 OK\n"
                    "- 3~4회 나눠서 하락 시마다 소량 추가\n"
                    "- 리스크: 하락 추세 고착 시 손실 확대 → 손절 규칙 병행\n"
                )
            else:
                plan = f"[{action}]을(를) 선택하셨어요. 세부 실행안을 원하시면 알려 주세요."

            ctx["portfolio_answer"] = (
                f"선택하신 옵션: {pick}번 {action}\n\n" + plan
            )
            ctx["strategy"] = None
            return ctx

    # 4) pick이 없으면 안내 + 선택지 제시
    lines = [
        f"가장 리스크가 커 보이는 종목은 {worst_ticker} 입니다.",
        f"- 평가손익률: {worst_ret:.1f}%",
        f"- 포트폴리오 비중: {worst_w:.1f}%",
        "",
        "선택지: ① 비중 축소 ② 손절/트레일링 ③ 헷지 ④ 분할매수",
        "→ 원하시면 숫자로 골라주세요. 예: '1번으로 해줘'",
    ]
    ctx["portfolio_answer"] = "\n".join(lines)
    ctx["strategy"] = None
    return ctx

def _present_candidates(ctx):
    """
    외부에서 strategies가 들어온 경우 목록을 보여주고,
    pick이 있으면 해당 전략을 '선택됨'으로 반영.
    """
    raw_list = ctx.get("input", {}).get("strategies") or ctx.get("strategies") or []
    cands = normalize_candidates(raw_list)
    ctx["strategies"] = cands

    # 👉 사용자가 고를 수 있게 choices를 저장
    ctx["choices"] = [{"id": s["id"], "label": s["label"]} for s in cands]

    pick = (ctx.get("input") or {}).get("pick")
    lines = []

    if not cands:
        lines.append("전략 후보가 없습니다. JSON으로 후보를 넣고 테스트해보세요.")
        ctx["strategy_answer"] = "\n".join(lines)
        ctx["strategy"] = None
        return ctx

    if pick:
        chosen = next((s for s in cands if str(pick) in (s.get("id"),)), None)
        if chosen:
            ctx["strategy"] = chosen
            lines.append(f"선택하신 전략: {chosen['id']} - {chosen['label']}")
            if chosen.get("rationale"):
                lines.append(f"- 근거: {chosen['rationale']}")
            if chosen.get("target_allocations"):
                lines.append(f"- 타깃 비중: {chosen['target_allocations']}")
            lines.append("→ 필요하시면 '시뮬 돌려줘'라고 해보세요.")
        else:
            lines.append("해당 ID의 전략을 찾지 못했습니다. 표시된 ID로 골라주세요.")
            ctx["strategy"] = None
    else:
        # 아직 안 골랐으면 번호/ID 안내
        lines.append("전략 후보:")
        for i, s in enumerate(cands, start=1):
            lines.append(f"{i}. {s['id']} — {s['label']}")
        lines.append("\n→ 예: '1번으로 해줘' 또는 'S2 선택'")

    ctx["strategy_answer"] = "\n".join(lines)
    return ctx

def choose_strategy(ctx):
    if needs_portfolio_qa(ctx):
        return _answer_portfolio_qa(ctx)

    if needs_strategy(ctx):
        return _present_candidates(ctx)

    ctx["strategy"] = None
    ctx["strategies"] = []
    return ctx