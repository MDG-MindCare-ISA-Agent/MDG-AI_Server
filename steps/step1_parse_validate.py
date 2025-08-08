# steps/step1_parse_validate.py (추가/교체)
from services.profile_service import load_profile, portfolio_allocations

def parse_and_validate(ctx):
    text = str(ctx.get("input", {}).get("text") or "")
    inv  = str(ctx.get("input", {}).get("investment") or "")
    ctx.setdefault("input", {})
    ctx["input"]["text"] = f"{text} [1단계: 입력검증]"
    ctx["input"]["investment"] = inv

    # 👇 프로필 로드 & 포트폴리오 비중 주입
    profile = load_profile(user_id="demo")
    ctx["profile"] = profile
    ctx["input"]["portfolio"] = portfolio_allocations(profile)
    return ctx