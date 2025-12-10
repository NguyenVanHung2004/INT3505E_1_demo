from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/callback', methods=['POST'])
def callback():
    data = request.json
    print("\n" + "="*40)
    print(f" [CLIENT] NHẬN ĐƯỢC WEBHOOK!")
    print(f" Sự kiện: {data.get('event')}")
    print(f" Thời gian: {data.get('timestamp')}")
    print(f" Dữ liệu: {data.get('data')}")
    print("="*40 + "\n")
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    print(">>> CLIENT CHẠY TẠI PORT 5001 <<<")
    app.run(port=5001)