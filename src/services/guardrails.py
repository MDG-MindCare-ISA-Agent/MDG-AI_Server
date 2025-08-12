FORBIDDEN_TRIGGERS = [
  "수익 보장","수익률 몇%","몇 % 오를까요","이 종목 사요","이 종목 팔아요",
  "지금 사도 될까요","세금 확답","정확한 세율","단기 급등","몰빵","전액","원금 회복 확실"
]

def triggered(text: str) -> bool:
    return any(k in text for k in FORBIDDEN_TRIGGERS)

def reply() -> str:
    return ("지금 마음이 많이 흔들리시는 것 같아 얼마나 힘드실지 짐작돼요. "
            "구체 조언보다 감정을 먼저 다독이면 도움이 크니, 괜찮으시다면 지금 불안을 가장 키운 한 가지 상황만 함께 정리해볼까요?")