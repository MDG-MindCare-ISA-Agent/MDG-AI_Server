from services.emotion_service import analyze_with_hyperclova
from services.memory_service import get_profile, set_profile

def _merge_profile(prev, now):
    # 아주 심플한 스무딩(원하면 EMA로 확장)
    prev = prev or {"감정":"중립","성향":"중립적","count":0}
    prev["count"] = prev.get("count",0)+1
    prev["감정"] = now.get("primary") or now.get("감정") or prev["감정"]
    prev["성향"] = now.get("성향") or prev["성향"]
    return prev

def analyze_emotion(ctx):
    """
    2단계: 감정/의도 분석
    CLOVA 키가 없으면 로컬 폴백으로 'type'을 뽑아냄.
    """
    if ctx.get("force_pick"):
        ctx["emotion"] = {"type":"info","primary":"중립","confidence":0.0,"triggers":[],"message":""}
        return ctx
    text = ctx.get("input", {}).get("text", "")
    if not text:
        ctx["emotion"] = {"type": "info", "primary": "중립", "confidence": 0.0, "triggers": [], "message": ""}
        return ctx

    result = analyze_with_hyperclova(text)  # 기존 그대로

    cid = (ctx.get("_meta") or {}).get("convo_id")
    prof_prev = get_profile(cid)
    # 모델 결과를 단일 스키마로 정리 (emotion/advice 등 혼용 대비)
    norm = {
        "감정": result.get("primary") or "중립",
        "성향": result.get("tendency") or result.get("tendency_guess") or None
    }
    prof_new = _merge_profile(prof_prev, norm)
    set_profile(cid, prof_new)

    # 다음 스텝들이 쓰도록 컨텍스트에 실어줌
    ctx["emotion"] = result
    ctx["profile_running"] = prof_new
    return ctx