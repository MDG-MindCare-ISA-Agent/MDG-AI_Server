# src/services/hyperclova_client.py
import uuid
import requests
from ..config import get_settings

_settings = get_settings()

def chat(messages, max_tokens=1024, temperature=0.7, top_p=0.8) -> str | None:
    url = f"https://clovastudio.stream.ntruss.com/testapp/v3/chat-completions/{_settings.HCX_MODEL_NAME}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_settings.HCX_API_KEY}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
    }
    payload = {"messages": messages, "topP": top_p, "temperature": temperature, "maxTokens": max_tokens}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        # 인증 실패 등은 None 반환해서 상위에서 친절 메시지로 대체
        if res.status_code == 401:
            # 로그가 필요하면 여기서 print(res.text) 혹은 logger.warning(...)
            return None
        res.raise_for_status()
        return res.json().get("result", {}).get("message", {}).get("content") or None
    except Exception:
        return None