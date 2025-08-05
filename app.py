from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "🎉 AI 서버가 실행 중입니다!"

@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.json
    investment = data.get("investment", 1000000)
    rate = data.get("rate", 0.05)
    profit = investment * rate
    after_tax = profit * 0.9
    return jsonify({
        "예상수익": round(profit),
        "세후수익": round(after_tax)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)