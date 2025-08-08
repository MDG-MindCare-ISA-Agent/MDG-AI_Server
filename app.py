from flask import Flask, request, jsonify, render_template_string, session
from pipeline import run_pipeline
from services.memory_service import get_convo_id, reset_memory, load_history

app = Flask(__name__)
app.secret_key = "change-me-please"  # 개발용. 실제 배포는 환경변수 사용 권장.
# reloader 켜면 인메모리 히스토리 날아가므로 아래 if __name__ == "__main__"에서 use_reloader=False 사용!

CHAT_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>ForAI Chat</title>
<style>
  body { font-family: system-ui, Arial, sans-serif; margin:0; background:#f6f7f9;}
  .wrap { max-width: 820px; margin: 0 auto; padding: 16px; }
  h1 { margin: 8px 0 12px; }
  #log { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:12px; height:70vh; overflow:auto; }
  .row { margin:10px 0; display:flex; }
  .msg { padding:10px 12px; border-radius:12px; max-width: 75%; white-space:pre-wrap; word-break:break-word; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
  .user .msg { margin-left:auto; background:#111827; color:#fff; }
  .assistant .msg { margin-right:auto; background:#f3f4f6; }
  .bar { display:flex; gap:8px; margin-top:12px; }
  .bar input { flex:1; padding:12px; border:1px solid #d1d5db; border-radius:10px; }
  .bar button { padding:12px 16px; border-radius:10px; border:1px solid #111827; background:#111827; color:#fff; cursor:pointer; }
  .bar button.secondary { background:#fff; color:#111827; border-color:#d1d5db; }
</style>
</head>
<body>
<div class="wrap">
  <h1>ForAI (Chat)</h1>
  <div id="log"></div>
  <div class="bar">
    <input id="text" placeholder="여기에만 입력하세요. 예: '전략 추천해줘' → 다음엔 '1번으로 해줘'"/>
    <button onclick="send()">보내기</button>
    <button class="secondary" onclick="resetMem()">Reset</button>
  </div>
</div>

<script>
async function reloadLog(scroll=true) {
  const res = await fetch('/api/history');
  const data = await res.json();
  const log = document.getElementById('log');
  log.innerHTML = '';

  for (const turn of data.history) {
    // user
    const user = document.createElement('div');
    user.className = 'row user';
    user.innerHTML = '<div class="msg"></div>';
    user.querySelector('.msg').textContent = (turn.user?.text || '').trim() || '(빈 메시지)';
    log.appendChild(user);

    // assistant
    const asst = document.createElement('div');
    asst.className = 'row assistant';
    asst.innerHTML = '<div class="msg"></div>';
    let answer = (turn.assistant?.answer || turn.assistant?.message || '').trim();
    if (!answer) answer = JSON.stringify(turn.assistant, null, 2);
    asst.querySelector('.msg').textContent = answer;
    log.appendChild(asst);
  }

  if (scroll) log.scrollTop = log.scrollHeight;
}

async function send() {
  const textEl = document.getElementById('text');
  const text = textEl.value || '';
  if (!text.trim()) return;

  const res = await fetch('/api/send', {
    method:'POST',
    headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({ text })
  });
  const data = await res.json();
  if (!data.ok && data.ok !== undefined) {
    alert('에러: ' + (data.message || 'unknown'));
    return;
  }
  textEl.value = '';
  await reloadLog(true);
}

async function resetMem() {
  const res = await fetch('/api/reset', { method:'POST' });
  const data = await res.json();
  alert(data.answer || '초기화됨');
  await reloadLog(false);
}

reloadLog(true);
</script>
</body>
</html>
"""

@app.route("/chat", methods=["GET"])
def chat_page():
    _ = get_convo_id(session)  # 세션/대화ID 확보
    return render_template_string(CHAT_HTML)

# 히스토리 조회
@app.route("/api/history", methods=["GET"])
def api_history():
    cid = get_convo_id(session)
    hist = load_history(cid)
    return jsonify({"ok": True, "history": hist})

# 한 줄 입력만 받음 (text)
@app.route("/api/send", methods=["POST"])
def api_send():
    cid = get_convo_id(session)
    try:
        data = request.get_json(silent=True) or {}
        # payload는 { "text": "사용자 문장 한 줄" } 만 보냄
        output = run_pipeline("isa_advice", {"text": data.get("text", "")}, convo_id=cid)
        return jsonify(output), 200
    except Exception as e:
        return jsonify({"ok": False, "error": type(e).__name__, "message": str(e)}), 400

# 초기화
@app.route("/api/reset", methods=["POST"])
def api_reset():
    cid = get_convo_id(session)
    reset_memory(cid)
    return jsonify({"ok": True, "answer": "대화 메모리를 초기화했어요."})

if __name__ == "__main__":
    # reloader 켜면 인메모리 히스토리 날아감
    app.run(debug=True, use_reloader=False)