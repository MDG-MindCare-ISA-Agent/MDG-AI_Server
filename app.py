from flask import Flask, request, jsonify, render_template_string
from pipeline import run_pipeline

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def root():
    # HTML Form 입력을 받아 파이프라인 실행
    # 출력 결과를 HTML로 렌더링
    pass

@app.route("/run", methods=["POST"])
def run_api():
    # JSON 입력을 받아 파이프라인 실행
    # 결과를 JSON으로 반환
    pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)