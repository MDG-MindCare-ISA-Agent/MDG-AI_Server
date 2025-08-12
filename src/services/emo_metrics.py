import time

EMA_ALPHA = 0.3
ANXIETY_THRESHOLD = 0.70
LOSS_AVERSION_THRESHOLD = 0.60

class EmoMeter:
    def __init__(self):
        self.anxiety = 0.0
        self.loss_aversion = 0.0
        self.cooldown_active = False
        self.cooldown_turns_left = 0
        self.cooldown_seconds_until = 0.0
        self.COOLDOWN_TURNS = 3
        self.COOLDOWN_SECONDS = 0

    def detect(self, text: str):
        emotion = "중립"
        if any(k in text for k in ["불안","초조","잠이","무섭","떨리"]): emotion="불안"
        if any(k in text for k in ["후회","망했","큰일"]): emotion="후회"
        if any(k in text for k in ["혼란","헷갈","모르겠"]): emotion="혼란"
        if any(k in text for k in ["기대","설레","희망"]): emotion="기대"
        signals=[]
        if any(k in text for k in ["해지","손절","전액","몰빵"]): signals.append("충동결정")
        if "추가 매수" in text or "물타기" in text: signals.append("추가매수고민")
        return {"emotion": emotion, "signals": signals}

    def _raw(self, tags):
        anxiety_raw = 1.0 if tags["emotion"] in ["불안","후회","혼란"] else 0.2
        loss_raw = 1.0 if "충동결정" in tags["signals"] else 0.0
        return anxiety_raw, loss_raw

    def update(self, text: str):
        tags = self.detect(text)
        a_raw, l_raw = self._raw(tags)
        self.anxiety = EMA_ALPHA*a_raw + (1-EMA_ALPHA)*self.anxiety
        self.loss_aversion = EMA_ALPHA*l_raw + (1-EMA_ALPHA)*self.loss_aversion

    def tick(self):
        if self.cooldown_active:
            if self.COOLDOWN_SECONDS > 0:
                if time.time() >= self.cooldown_seconds_until:
                    self.cooldown_active=False; self.cooldown_turns_left=0; self.cooldown_seconds_until=0.0
            else:
                self.cooldown_turns_left -= 1
                if self.cooldown_turns_left <= 0:
                    self.cooldown_active=False

    def need_intervention(self) -> bool:
        if self.cooldown_active: return False
        return (self.anxiety>ANXIETY_THRESHOLD) or (self.loss_aversion>LOSS_AVERSION_THRESHOLD)

    def start_cooldown(self):
        self.cooldown_active=True
        self.cooldown_turns_left=self.COOLDOWN_TURNS
        if self.COOLDOWN_SECONDS>0:
            self.cooldown_seconds_until=time.time()+self.COOLDOWN_SECONDS

def intervention_text() -> str:
    return "혹시 1분만 호흡을 같이 해볼까요? 끝나면 ‘결정 보류’나 ‘리프레이밍’, ‘ISA 체크리스트’ 중 하나로 오늘 마음을 정리해도 좋아요."