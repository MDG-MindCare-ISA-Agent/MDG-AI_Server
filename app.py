# app.py
from flask import Flask, request, jsonify, render_template_string
from pipeline import run_pipeline
import json

app = Flask(__name__)

HTML_FORM = """
<!doctype html><meta charset="utf-8">
<title>AI 파이프라인 테스트</title>
<h1>AI 파이프라인 테스트</h1>
<form method="post" action="/">
  <label>텍스트</label><br>
  <input name="text" value="{{ text or '요즘 하락이 불안해요' }}" style="width: 320px"><br><br>
  <label>투자금(원)</label><br>
  <input name="investment" value="{{ investment or '1500000' }}"><br><br>
  <button type="submit">실행</button>
</form>

{% if result is not none %}
  <hr>
  <h2>결과</h2>
  <pre>{{ result }}</pre>
{% endif %}
"""

@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        text = request.form.get("text", "")
        investment = request.form.get("investment", "0")

        ctx = run_pipeline("isa_advice", {"text": text, "investment": investment})
        output = ctx.get("output")
        if output is None:
            return render_template_string(HTML_FORM, text=text, investment=investment, result="에러: output 없음"), 500

        result_str = json.dumps(output, indent=2, ensure_ascii=False)
        return render_template_string(HTML_FORM, text=text, investment=investment, result=result_str)

    # GET
    return render_template_string(HTML_FORM, text=None, investment=None, result=None)

@app.route("/run", methods=["POST"])
def run_api():
    body = request.get_json(silent=True) or {}
    pipeline_name = body.get("pipeline", "isa_advice")
    payload = body.get("input", {})

    try:
        ctx = run_pipeline(pipeline_name, payload)
        return jsonify({"ok": True, "result": ctx.get("output"), "meta": ctx.get("_meta")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)