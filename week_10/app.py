from flask import Flask, request, jsonify
from models import db, Book, Member, Loan
import requests
import threading
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library_full.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- KHU VỰC 1: CẤU HÌNH WEBHOOK & HATEOAS ---

# Lưu danh sách người đăng ký webhook (In-memory)
subscribers = []

def trigger_webhook(event_type, payload):
    """Gửi sự kiện cho các bên đăng ký (Pattern: Event-driven/Webhook)"""
    def send():
        print(f"\n[Webhook System] Đang bắn sự kiện '{event_type}'...")
        for sub in subscribers:
            if sub['event'] == event_type:
                try:
                    requests.post(sub['url'], json={
                        "event": event_type,
                        "timestamp": datetime.now().isoformat(),
                        "data": payload
                    }, timeout=1)
                    print(f" -> Đã gửi tới {sub['url']}")
                except:
                    print(f" -> Lỗi khi gửi tới {sub['url']}")
    
    thread = threading.Thread(target=send)
    thread.start()

def hateoas_response(data, resource_type, resource_id=None):
    """Bọc dữ liệu trả về với các link điều hướng (Pattern: HATEOAS)"""
    base = request.host_url.rstrip('/')
    links = {}

    if resource_id:
        # Link cho Single Item
        links['self'] = f"{base}/{resource_type}/{resource_id}"
        links['collection'] = f"{base}/{resource_type}"
        links['update'] = {"href": f"{base}/{resource_type}/{resource_id}", "method": "PUT"}
        links['delete'] = {"href": f"{base}/{resource_type}/{resource_id}", "method": "DELETE"}
    else:
        # Link cho Collection
        links['self'] = request.url
        links['create'] = {"href": f"{base}/{resource_type}", "method": "POST"}

    return {"data": data, "_links": links}

# --- KHU VỰC 2: API QUẢN LÝ SÁCH (BOOKS) ---

@app.route('/books', methods=['GET'])
def get_books():
    # Pattern: Query (Lọc theo tác giả hoặc trạng thái)
    author = request.args.get('author')
    status = request.args.get('status')
    
    query = Book.query
    if author: query = query.filter(Book.author.contains(author))
    if status: query = query.filter_by(status=status.upper())
    
    books = query.all()
    # Trả về list kèm HATEOAS cho từng phần tử
    result = [hateoas_response(b.to_dict(), 'books', b.id) for b in books]
    return jsonify({"count": len(result), "items": result})

@app.route('/books', methods=['POST'])
def create_book():
    data = request.json
    new_book = Book(title=data['title'], author=data['author'])
    db.session.add(new_book)
    db.session.commit()
    
    # Trigger Webhook
    trigger_webhook("book_added", new_book.to_dict())
    
    return jsonify(hateoas_response(new_book.to_dict(), 'books', new_book.id)), 201

@app.route('/books/<int:id>', methods=['PUT'])
def update_book(id):
    book = db.get_or_404(Book, id)
    data = request.json
    book.title = data.get('title', book.title)
    book.author = data.get('author', book.author)
    db.session.commit()
    return jsonify(hateoas_response(book.to_dict(), 'books', id))

@app.route('/books/<int:id>', methods=['DELETE'])
def delete_book(id):
    book = db.get_or_404(Book, id)
    db.session.delete(book)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200

# --- KHU VỰC 3: API QUẢN LÝ THÀNH VIÊN (MEMBERS) ---

@app.route('/members', methods=['GET'])
def get_members():
    members = Member.query.all()
    result = [hateoas_response(m.to_dict(), 'members', m.id) for m in members]
    return jsonify(result)

@app.route('/members', methods=['POST'])
def create_member():
    data = request.json
    new_member = Member(name=data['name'], email=data['email'])
    try:
        db.session.add(new_member)
        db.session.commit()
        trigger_webhook("member_registered", new_member.to_dict())
        return jsonify(hateoas_response(new_member.to_dict(), 'members', new_member.id)), 201
    except:
        return jsonify({"error": "Email already exists"}), 400

# --- KHU VỰC 4: API MƯỢN TRẢ (LOANS) - Logic phức tạp nhất ---

@app.route('/loans', methods=['POST'])
def create_loan():
    """Mượn sách"""
    data = request.json
    book = db.session.get(Book, data['book_id'])
    member = db.session.get(Member, data['member_id'])
    
    if not book or not member:
        return jsonify({"error": "Invalid Book or Member ID"}), 400
    if book.status != 'AVAILABLE':
        return jsonify({"error": "Book is already borrowed"}), 400

    # Tạo phiếu mượn
    loan = Loan(book_id=book.id, member_id=member.id)
    book.status = 'BORROWED' # Update status sách
    
    db.session.add(loan)
    db.session.commit()
    
    # Trigger Webhook
    payload = {
        "loan_id": loan.id,
        "book_title": book.title,
        "member_name": member.name
    }
    trigger_webhook("loan_created", payload)
    
    return jsonify(hateoas_response(loan.to_dict(), 'loans', loan.id)), 201

@app.route('/loans/<int:id>/return', methods=['PUT'])
def return_book(id):
    """Trả sách"""
    loan = db.get_or_404(Loan, id)
    if loan.return_date:
        return jsonify({"error": "Loan already returned"}), 400
        
    loan.return_date = datetime.now().strftime('%Y-%m-%d')
    
    # Cập nhật lại sách thành AVAILABLE
    book = db.session.get(Book, loan.book_id)
    book.status = 'AVAILABLE'
    
    db.session.commit()
    
    # Trigger Webhook
    trigger_webhook("loan_returned", loan.to_dict())
    
    return jsonify(hateoas_response(loan.to_dict(), 'loans', id))

@app.route('/loans', methods=['GET'])
def get_loans():
    # Query Pattern: Lọc theo member_id
    member_id = request.args.get('member_id')
    query = Loan.query
    if member_id:
        query = query.filter_by(member_id=member_id)
    
    loans = query.all()
    return jsonify([hateoas_response(l.to_dict(), 'loans', l.id) for l in loans])

# --- KHU VỰC 5: ĐĂNG KÝ WEBHOOK ---

@app.route('/webhooks', methods=['POST'])
def register_webhook():
    """
    Client gọi API này để đăng ký nhận thông báo.
    Body: {"url": "http://localhost:5001/callback", "event": "loan_created"}
    """
    data = request.json
    subscribers.append(data)
    return jsonify({"message": "Webhook subscribed!", "sub": data}), 201

@app.route('/setup_db', methods=['GET'])
def setup():
    """Helper để tạo DB nhanh"""
    with app.app_context():
        db.create_all()
    return jsonify({"message": "Database Created Successfully"})

if __name__ == '__main__':
    print(">>> SERVER CHẠY TẠI PORT 5000 <<<")
    app.run(port=5000, debug=True)