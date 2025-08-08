# steps/step3a_fetch_info.py
from routing import needs_info
from services.info_service import get_market_snapshot

def fetch_info(ctx):
    if not needs_info(ctx):
        return ctx
    q = ctx.get("input", {}).get("text", "")
    ctx["info"] = get_market_snapshot(q)
    return ctx