import logging
import time
from datetime import datetime
import threading
import requests
from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# --- 1. CONFIG MONITORING (LOGGING) ---
# Thiết lập log ra file 'system.log' và cả màn hình console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("LibraryApp")

# --- 2. CONFIG PROMETHEUS METRICS ---
# Tự động đo đạc latency và count request, xem tại endpoint /metrics
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Application info', version='1.0.0')

# --- 3. CONFIG RATE LIMITING ---
# Chặn spam: Dùng địa chỉ IP để định danh user
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"], # Mặc định cho toàn app
    storage_uri="memory://"
)

# --- DATABASE SETUP (Giống Week 10) ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library_prod.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='AVAILABLE')

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.String(50))

# --- 4. CIRCUIT BREAKER PATTERN (Tự chế đơn giản) ---
class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=10):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED (Bình thường), OPEN (Ngắt mạch)

    def call(self, url, payload):
        # Nếu mạch đang mở (OPEN), kiểm tra xem đã hết thời gian chờ chưa
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit Breaker: Đang thử kết nối lại (HALF-OPEN)...")
                self.state = "HALF-OPEN"
            else:
                logger.warning("Circuit Breaker: Mạch đang ngắt. Bỏ qua Webhook.")
                return False

        try:
            # Gửi request
            response = requests.post(url, json=payload, timeout=1)
            response.raise_for_status()
            
            # Nếu thành công, reset trạng thái
            self.failure_count = 0
            self.state = "CLOSED"
            logger.info(f"Webhook gửi thành công tới {url}")
            return True
            
        except Exception as e:
            self.failure_count += 1
            logger.error(f"Webhook lỗi ({self.failure_count}/{self.failure_threshold}): {str(e)}")
            
            # Nếu lỗi quá ngưỡng, mở mạch (ngắt kết nối)
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_failure_time = time.time()
                logger.critical("Circuit Breaker: ĐÃ NGẮT MẠCH! Hệ thống sẽ dừng gọi Webhook.")
            return False

# Khởi tạo Circuit Breaker
webhook_breaker = CircuitBreaker()
WEBHOOK_URL = "http://localhost:5001/notify" # Giả định server webhook

# --- ROUTES ---

@app.before_request
def start_timer():
    g.start = time.time()

@app.after_request
def log_request(response):
    """Middleware: Log mọi request sau khi xử lý xong"""
    now = time.time()
    duration = round(now - g.start, 2)
    ip = request.remote_addr
    method = request.method
    path = request.path
    status = response.status_code
    
    # Ghi log chuẩn production
    logger.info(f"IP: {ip} | {method} {path} | Status: {status} | Duration: {duration}s")
    return response

@app.route('/setup')
def setup():
    with app.app_context():
        db.create_all()
        if not Book.query.first():
            db.session.add(Book(title="DevOps Handbook"))
            db.session.add(Book(title="SRE Google"))
            db.session.commit()
    return jsonify({"msg": "Database Ready"})

@app.route('/books', methods=['GET'])
# RATE LIMIT: Endpoint này cho phép gọi thoải mái
def get_books():
    books = Book.query.all()
    return jsonify([{"id": b.id, "title": b.title, "status": b.status} for b in books])

@app.route('/loans', methods=['POST'])
# RATE LIMIT: Endpoint quan trọng, giới hạn 5 lần/phút để chống spam
@limiter.limit("5 per minute")
def create_loan():
    data = request.json
    book_id = data.get('book_id')
    
    # Simulate processing time
    time.sleep(0.1) 
    
    loan = Loan(book_id=book_id, timestamp=str(datetime.now()))
    db.session.add(loan)
    db.session.commit()
    
    # Xử lý Webhook thông qua Circuit Breaker
    # (Chạy thread riêng để không block user, nhưng breaker vẫn quản lý trạng thái chung)
    def notify():
        webhook_breaker.call(WEBHOOK_URL, {"event": "loan_created", "book_id": book_id})
    
    threading.Thread(target=notify).start()
    
    return jsonify({"msg": "Loan created", "loan_id": loan.id}), 201

# Endpoint giả lập lỗi để test logs
@app.route('/error')
def trigger_error():
    logger.error("User truy cập vào endpoint lỗi!")
    1 / 0 # Cố tình gây lỗi 500
    return "Error"

if __name__ == '__main__':
    print(">>> PRODUCTION API RUNNING ON PORT 5000 <<<")
    # Tắt debug mode để giả lập production thực tế hơn
    app.run(port=5000, debug=False)