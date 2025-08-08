import re

# 간단 키워드로 바리에이션 커버
RE_QA = re.compile(r"(가장\s*불안|가장\s*걱정|워스트|손실|마이너스|어느\s*종목이\s*문제|비중\s*너무|평단|수익률|손익)", re.I)

def derive_plan(ctx):
    text = (ctx.get("input") or {}).get("text", "") or ""
    emo  = ctx.get("emotion") or {}
    t    = (emo.get("type") or "info").lower()
    want_sim = bool(ctx.get("input", {}).get("simulate") or ctx.get("input", {}).get("want_simulation"))

    plan = {"info": False, "strategy": False, "simulation": False, "portfolio_qa": False}

    # 1) 텍스트가 Q&A를 강하게 시사하면 최우선으로 Q&A
    if RE_QA.search(text):
        plan["portfolio_qa"] = True
        ctx["_plan"] = plan
        return ctx

    # 2) 감정 결과에 세부 의도(analysis_subtype)가 있으면 반영
    subtype = (emo.get("analysis_subtype") or "").lower()
    if t == "analysis":
        if subtype in ("qa", "question", "diagnose", "check"):
            plan["portfolio_qa"] = True
        elif subtype in ("optimize", "rebalance", "strategy"):
            plan["strategy"] = True
            plan["simulation"] = False  # 전략 먼저 추천
        else:
            plan["portfolio_qa"] = True
        ctx["_plan"] = plan
        return ctx

    # 3) 나머지 기본 라우팅
    if t == "info":
        plan["info"] = True
    elif t in ("advice", "goal"):
        plan["strategy"] = True
        plan["simulation"] = False
    elif t == "system":
        pass
    elif t == "emotion":
        pass
    else:
        plan["info"] = True

    ctx["_plan"] = plan
    return ctx

def needs_info(ctx):         return bool(ctx.get("_plan", {}).get("info"))
def needs_strategy(ctx):     return bool(ctx.get("_plan", {}).get("strategy"))
def needs_simulation(ctx):   return bool(ctx.get("_plan", {}).get("simulation"))
def needs_portfolio_qa(ctx): return bool(ctx.get("_plan", {}).get("portfolio_qa"))