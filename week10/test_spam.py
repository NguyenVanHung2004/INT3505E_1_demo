import requests
import time

BASE_URL = "http://localhost:5000"

print("--- 1. TEST RATE LIMIT (Spam mượn sách) ---")
# API chỉ cho phép 5 lần/phút. Ta sẽ bắn 8 lần.
for i in range(1, 9):
    try:
        res = requests.post(f"{BASE_URL}/loans", json={"book_id": 1})
        if res.status_code == 201:
            print(f"Request {i}: Thành công")
        elif res.status_code == 429:
            print(f"Request {i}: BỊ CHẶN (Rate Limit) - {res.text.strip()}")
        else:
            print(f"Request {i}: Code {res.status_code}")
    except Exception as e:
        print(f"Lỗi kết nối: {e}")
    time.sleep(0.2)

print("\n--- 2. TEST CIRCUIT BREAKER (Mở Logs server để xem) ---")
print("Webhooks đang được bắn ngầm. Nếu server nhận (port 5001) tắt, Circuit Breaker sẽ kích hoạt.")