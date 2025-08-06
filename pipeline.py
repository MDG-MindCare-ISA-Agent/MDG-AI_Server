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
    # name에 해당하는 파이프라인 실행
    # 각 step은 ctx(dict)를 입력받아 수정 후 반환
    pass