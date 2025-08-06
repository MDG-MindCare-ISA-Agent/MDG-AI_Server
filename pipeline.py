from typing import Callable, Dict, Any
from steps.step1_parse_validate import parse_and_validate
from steps.step2_analyze_emotion import analyze_emotion
from steps.step3_choose_strategy import choose_strategy
from steps.step4_simulate_return import simulate_return
from steps.step5_format_output import format_output

# 파이프라인 정의 (단계 순서)
PIPELINES = {
    "isa_advice": [
        parse_and_validate,
        analyze_emotion,
        choose_strategy,
        simulate_return,
        format_output
    ]
}

def run_pipeline(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if name not in PIPELINES:
        raise ValueError(f"unknown pipeline: {name}")

    ctx: Dict[str, Any] = {"input": payload, "_meta": {"pipeline": name}}

    for i, step in enumerate(PIPELINES[name], start=1):
        ctx = step(ctx)
        if ctx is None or not isinstance(ctx, dict):
            raise TypeError(f"Step {i} ({step.__name__}) returned invalid ctx: {ctx!r}")

    if "output" not in ctx:
        raise KeyError("Pipeline finished but ctx['output'] is missing")

    return ctx