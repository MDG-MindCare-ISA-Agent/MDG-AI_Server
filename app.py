from flask import Flask, request, jsonify, render_template_string
from pipeline import run_pipeline

app = Flask(__name__)

HTML = """
<!doctype html>
<title>ForAI</title>
<h1>테스트 폼</h1>
<form method="post">
  <input name="text" placeholder="텍스트" style="width:400px" />
  <input name="investment" placeholder="투자금(선택)" />
  <input name="chosen_strategy" placeholder="선택한 전략번호(선택)" />
  <button type="submit">Run</button>
</form>
{% if result %}
  <hr/>
  <h2>결과</h2>
  {% if result.answer %}
    <pre style="white-space: pre-wrap;">{{ result.answer }}</pre>
  {% endif %}
  <details style="margin-top:12px;">
    <summary>디버그(JSON 보기)</summary>
    <pre>{{ result | tojson(indent=2) }}</pre>
  </details>
{% endif %}
"""

@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "GET":
        return render_template_string(HTML)

    try:
        text = request.form.get("text", "")
        investment = request.form.get("investment")
        chosen_strategy = request.form.get("chosen_strategy")

        payload = {
            "text": text,
            "investment": investment,
        }

        if chosen_strategy:
            payload["simulate"] = True
            payload["chosen_strategy"] = chosen_strategy

        output = run_pipeline("isa_advice", payload)

        want_json = request.args.get("format") == "json"
        if want_json:
            return jsonify(output), 200
        else:
            return render_template_string(HTML, result=output), 200

    except Exception as e:
        return jsonify({"ok": False, "error": type(e).__name__, "message": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True)