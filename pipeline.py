# pipeline.py
import time
from copy import deepcopy
from typing import Callable, Dict, Any
from steps.step1_parse_validate import parse_and_validate
from steps.step2_analyze_emotion import analyze_emotion
from steps.step2b_route_plan import route_plan
from steps.step3a_fetch_info import fetch_info 
from steps.step3_choose_strategy import choose_strategy
from steps.step4_simulate_return import simulate_return
from steps.step5_format_output import format_output

DEBUG_PIPELINE = True  # 필요시 False

PIPELINES: Dict[str, list[Callable]] = {
    "isa_advice": [
        parse_and_validate,   # 1
        analyze_emotion,      # 2
        route_plan,      # 2.5 라우팅
        fetch_info,   
        choose_strategy,      # 3
        simulate_return,      # 4
        format_output,        # 5
    ]
}

def _short(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """콘솔에 찍을 때만 쓰는 축약본(민감값/대형리스트 제거)"""
    out = {}
    for k in ("input", "emotion", "strategy", "simulation"):
        if k not in ctx: 
            continue
        v = ctx[k]
        if k == "input":
            out[k] = {kk: ("<long>" if isinstance(vv, (list, dict)) and len(str(vv)) > 200 else vv)
                      for kk, vv in v.items()} if isinstance(v, dict) else "<non-dict>"
        elif k == "simulation" and isinstance(v, dict):
            copy = {**v}
            if "equity_curve" in copy and isinstance(copy["equity_curve"], list):
                copy["equity_curve"] = f"<list len={len(copy['equity_curve'])}>"
            out[k] = copy
        else:
            out[k] = v
    return out

def run_pipeline(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if name not in PIPELINES:
        raise ValueError(f"unknown pipeline: {name}")

    # 원본 보존
    ctx: Dict[str, Any] = {"input": deepcopy(payload), "_meta": {"pipeline": name, "ts": time.time()}}

    for i, step in enumerate(PIPELINES[name], start=1):
        t0 = time.time()
        try:
            ctx = step(ctx)
            if ctx is None or not isinstance(ctx, dict):
                raise TypeError(f"Step {i} ({step.__name__}) returned invalid ctx: {ctx!r}")
        except Exception as e:
            # 스텝에서 예외 발생 시 즉시 에러 응답 구성 (500 방지)
            ctx.setdefault("_errors", [])
            ctx["_errors"].append({
                "step": i,
                "name": step.__name__,
                "error": type(e).__name__,
                "message": str(e),
            })
            if DEBUG_PIPELINE:
                print(f"[PIPELINE][ERROR] step#{i} {step.__name__}: {type(e).__name__}: {e}")
                print(f"[PIPELINE][CTX-SHORT] after error: {_short(ctx)}")
            # 에러도 형식을 맞춰 반환하도록 output 생성
            ctx["output"] = {
                "ok": False,
                "error_step": step.__name__,
                "errors": ctx["_errors"],
                "emotion": ctx.get("emotion"),
                "strategy": ctx.get("strategy"),
                "simulation": ctx.get("simulation"),
                "_meta": ctx.get("_meta", {}),
            }
            return ctx["output"]

        dt = (time.time() - t0) * 1000
        if DEBUG_PIPELINE:
            # 스텝 통과 로그
            have = {k: (k in ctx) for k in ("emotion", "strategy", "simulation", "output")}
            print(f"[PIPELINE] step#{i} {step.__name__} ok in {dt:.1f}ms | keys={have}")
            print(f"[PIPELINE][CTX-SHORT] {_short(ctx)}")

    if "output" not in ctx:
        # 마지막 보강: output 누락시 에러 형태로 반환
        msg = "Pipeline finished but ctx['output'] is missing"
        if DEBUG_PIPELINE:
            print(f"[PIPELINE][ERROR] {msg}")
        return {
            "ok": False,
            "error_step": "format_output(missing)",
            "errors": [{"step": None, "name": "format_output", "error": "KeyError", "message": msg}],
            "emotion": ctx.get("emotion"),
            "strategy": ctx.get("strategy"),
            "simulation": ctx.get("simulation"),
            "_meta": ctx.get("_meta", {}),
        }

    # 정상 완료
    return {"ok": True, **ctx["output"]}