import re
from services.profile_service import load_profile, portfolio_allocations
from services.memory_service import get_last_options, summarize_history_for_prompt, is_awaiting_choice

RE_COMPOSITION = re.compile(r"(비율|구성|비중표|퍼센트|상위|톱|요약|분산|다변화|분포)", re.I)
RE_OTHER = re.compile(r"(다른|말고|추가|more)", re.I)

def parse_and_validate(ctx):
    # ✅ 원문(raw)을 따로 잡고, 이걸로 pick을 파싱한다
    raw_text = str((ctx.get("input") or {}).get("text") or "")
    inv = str((ctx.get("input") or {}).get("investment") or "")

    ctx.setdefault("input", {})
    ctx["input"]["investment"] = inv

    # 히스토리 요약 주입(있으면)
    hist = ctx.get("history") or []
    if hist:
        ctx["input"]["history_summary"] = summarize_history_for_prompt(hist)

    # ✅ 마지막 선택지 기반으로 raw_text에서 pick 해석
    convo_id = (ctx.get("_meta") or {}).get("convo_id")
    if convo_id:
        last_options = get_last_options(convo_id)  # [{id,label}, ...]
    else:
        last_options = []

    awaiting = is_awaiting_choice(convo_id) if convo_id else False
    picked_id = None
    norm = raw_text.strip()

    if last_options:
        # 1) “1번/2번/3번/1/2/3”
        m = re.match(r'^\s*(\d+)\s*번?\s*(?:해?줘?)?\s*$', norm)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(last_options):
                picked_id = last_options[idx]["id"]

        # 2) “S2/s3/전략2”
        if not picked_id:
            m = re.search(r'(?:S|s|전략)\s*(\d+)', norm)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(last_options):
                    picked_id = last_options[idx]["id"]

        # 3) 옵션 id 문자열이 직접 들어온 경우
        if not picked_id:
            tokens = re.findall(r'[A-Za-z0-9_-]+', norm)
            ids = {opt["id"] for opt in last_options if "id" in opt}
            for t in tokens:
                if t in ids:
                    picked_id = t
                    break

    if picked_id:
        ctx["input"]["pick"] = picked_id

    # ✅ 텍스트 자체로 구성요약 모드 힌트 (routing이 못 받았을 때를 대비)
    if RE_COMPOSITION.search(raw_text) or RE_OTHER.search(raw_text):
        ctx["_qa_mode_hint"] = "composition"

    # ✅ 이후 스텝(감정/라우팅 등)이 혼동 없도록 raw 그대로 사용
    #    (디버그 꼬리표는 별도 필드에만 보관)
    ctx["input"]["text"] = raw_text
    ctx["_debug_text_step1"] = f"{raw_text} [1단계: 입력검증]"

    # 프로필/포트폴리오 주입
    profile = load_profile(user_id="demo")
    ctx["profile"] = profile
    allocs = portfolio_allocations(profile)
    ctx["input"]["portfolio"] = allocs
    ctx["portfolio"] = allocs

    return ctx