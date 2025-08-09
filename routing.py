# routing.py
import re
from services.memory_service import is_awaiting_choice

# 기존 정규식들 그대로 두고 ↓ 추가
RE_GREETING = re.compile(r"^(안녕|안녕하세요|하이|hi|hello|헬로|ㅎㅇ|안뇽)\b", re.I)
RE_THANKS   = re.compile(r"(고마워|감사|땡큐|thanks|thank\s*you)", re.I)
RE_SMALLTALK = re.compile(r"(날씨|오늘 기분|심심|테스트|잘 지내|누구야|뭐야)", re.I)

RE_PF = re.compile(
    r"(포트폴리오|포폴|보유|내\s*종목|종목\s*분석|평단|수익률|손익|비중|비율|구성|비중표|퍼센트|"
    r"요약|상위|톱|분산|다변화|분포)",
    re.I
)
RE_STRAT = re.compile(
    r"(전략|리밸런싱|배분|할당|타[깃겟]?\s*비중|allocation|추천|플랜|계획)",
    re.I
)
RE_SIM = re.compile(r"(시뮬|백테스트|CAGR|변동성|맥스드로우다운|max\s*dd)", re.I)
RE_COMPOSITION = re.compile(r"(비율|구성|비중표|퍼센트|상위|톱|요약|분산|다변화|분포)", re.I)

def derive_plan(ctx):
    text = (ctx.get("input") or {}).get("text", "") or ""
    # 🔧 smalltalk 플래그 추가
    plan = {"smalltalk": False, "info": False, "strategy": False, "simulation": False, "portfolio_qa": False}

    convo_id = (ctx.get("_meta") or {}).get("convo_id")
    has_profile = bool((ctx.get("profile") or {}).get("holdings"))

    # 0) 직전 턴이 '선택 대기'면 pick만 받는다 → Q&A 고정
    if convo_id and is_awaiting_choice(convo_id):
        plan["portfolio_qa"] = True
        ctx["_plan"] = plan
        return ctx

    # 🎯 0.5) 인사/가벼운 스몰토크는 가장 먼저 분기
    if RE_GREETING.search(text) or RE_THANKS.search(text) or RE_SMALLTALK.search(text):
        plan["smalltalk"] = True
        ctx["_plan"] = plan
        return ctx

    # 1) 숫자/ID로 pick 들어오면 → Q&A 고정
    if (ctx.get("input") or {}).get("pick"):
        plan["portfolio_qa"] = True
        ctx["_plan"] = plan
        return ctx

    # 2) 포폴/종목 관련 키워드가 있으면 → 무조건 Q&A
    if has_profile and RE_PF.search(text):
        plan["portfolio_qa"] = True
        if RE_COMPOSITION.search(text):
            ctx["_qa_mode"] = "composition"
        ctx["_plan"] = plan
        return ctx

    # 3) 전략
    if RE_STRAT.search(text) or (ctx.get("input") or {}).get("strategies"):
        plan["strategy"] = True
        ctx["_plan"] = plan
        return ctx

    # 4) 시뮬
    if RE_SIM.search(text):
        plan["simulation"] = True
        ctx["_plan"] = plan
        return ctx

    # 5) 나머지 → info
    plan["info"] = True
    ctx["_plan"] = plan
    return ctx

def needs_smalltalk(ctx):    return bool(ctx.get("_plan", {}).get("smalltalk"))
def needs_info(ctx):         return bool(ctx.get("_plan", {}).get("info"))
def needs_strategy(ctx):     return bool(ctx.get("_plan", {}).get("strategy"))
def needs_simulation(ctx):   return bool(ctx.get("_plan", {}).get("simulation"))
def needs_portfolio_qa(ctx): return bool(ctx.get("_plan", {}).get("portfolio_qa"))