# cacheable_demo.py
from datetime import datetime, timedelta
import hashlib, json
from dateutil import tz
from flask import Flask, request, make_response, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///library.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ===== Models =====
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    author = db.Column(db.String, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    borrowed_at = db.Column(db.String, nullable=False)
    due_at = db.Column(db.String, nullable=False)
    returned_at = db.Column(db.String, nullable=True)

    book = db.relationship("Book")
    member = db.relationship("Member")

with app.app_context():
    db.create_all()

# ===== Helpers =====
def _json_bytes(obj) -> bytes:
    # Chuẩn hoá serialization để hash ổn định (không phụ thuộc spacing, order)
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8")

def _etag_of(obj) -> str:
    return hashlib.sha256(_json_bytes(obj)).hexdigest()

def json_cache(obj, status=200, max_age=120):
    """
    Trả JSON có kèm Cache-Control và ETag.
    Nếu If-None-Match khớp -> 304.
    """
    payload = obj  # dict/list
    etag = _etag_of(payload)
    inm = request.headers.get("If-None-Match")

    if inm and inm == etag:
        resp = make_response("", 304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = f"public, max-age={max_age}"
        return resp

    raw = _json_bytes(payload)
    resp = make_response(raw, status)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = f"public, max-age={max_age}"
    return resp

def now_iso():
    return datetime.now(tz.UTC).isoformat()

# ===== Books =====
@app.get("/books")
def list_books():
    items = [{"id": b.id, "title": b.title, "author": b.author, "stock": b.stock}
             for b in Book.query.order_by(Book.id).all()]
    # Danh sách thường cache ngắn hơn
    return json_cache({"items": items, "count": len(items)}, max_age=60)

@app.post("/books")
def create_book():
    data = request.get_json() or {}
    for f in ("title","author","stock"):
        if f not in data: return jsonify({"error": f"{f} required"}), 400
    b = Book(title=data["title"], author=data["author"], stock=int(data["stock"]))
    db.session.add(b); db.session.commit()
    # Không cache response ghi/PUT/POST
    return jsonify({"id": b.id, "title": b.title, "author": b.author, "stock": b.stock}), 201

@app.get("/books/<int:book_id>")
def get_book(book_id):
    b = Book.query.get(book_id)
    if not b: return jsonify({"error":"Not found"}), 404
    return json_cache({"id": b.id, "title": b.title, "author": b.author, "stock": b.stock}, max_age=300)

@app.put("/books/<int:book_id>")
def update_book(book_id):
    b = Book.query.get(book_id)
    if not b: return jsonify({"error":"Not found"}), 404
    data = request.get_json() or {}
    for f in ("title","author","stock"):
        if f not in data: return jsonify({"error": f"{f} required"}), 400
    b.title, b.author, b.stock = data["title"], data["author"], int(data["stock"])
    db.session.commit()
    return jsonify({"id": b.id, "title": b.title, "author": b.author, "stock": b.stock})

@app.delete("/books/<int:book_id>")
def delete_book(book_id):
    b = Book.query.get(book_id)
    if not b: return jsonify({"error":"Not found"}), 404
    db.session.delete(b); db.session.commit()
    return "", 204

# ===== Members =====
@app.get("/members")
def list_members():
    items = [{"id": m.id, "name": m.name, "email": m.email}
             for m in Member.query.order_by(Member.id.desc()).all()]
    return json_cache({"items": items, "count": len(items)}, max_age=90)

@app.post("/members")
def create_member():
    data = request.get_json() or {}
    for f in ("name","email"):
        if f not in data: return jsonify({"error": f"{f} required"}), 400
    if Member.query.filter_by(email=data["email"]).first():
        return jsonify({"error":"Email already exists"}), 409
    m = Member(name=data["name"], email=data["email"])
    db.session.add(m); db.session.commit()
    return jsonify({"id": m.id, "name": m.name, "email": m.email}), 201

@app.get("/members/<int:member_id>")
def get_member(member_id):
    m = Member.query.get(member_id)
    if not m: return jsonify({"error":"Not found"}), 404
    return json_cache({"id": m.id, "name": m.name, "email": m.email}, max_age=300)

@app.put("/members/<int:member_id>")
def update_member(member_id):
    m = Member.query.get(member_id)
    if not m: return jsonify({"error":"Not found"}), 404
    data = request.get_json() or {}
    for f in ("name","email"):
        if f not in data: return jsonify({"error": f"{f} required"}), 400
    if Member.query.filter(Member.email==data["email"], Member.id!=member_id).first():
        return jsonify({"error":"Email already exists"}), 409
    m.name, m.email = data["name"], data["email"]
    db.session.commit()
    return jsonify({"id": m.id, "name": m.name, "email": m.email})

@app.delete("/members/<int:member_id>")
def delete_member(member_id):
    m = Member.query.get(member_id)
    if not m: return jsonify({"error":"Not found"}), 404
    db.session.delete(m); db.session.commit()
    return "", 204

# ===== Loans =====
@app.get("/loans")
def list_loans():
    status = request.args.get("status","active")
    q = Loan.query
    if status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    else:
        q = q.filter(Loan.returned_at.is_(None))
    items = [{
        "id": l.id,
        "book_id": l.book_id, "book_title": l.book.title,
        "member_id": l.member_id, "member_name": l.member.name,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    } for l in q.order_by(Loan.id.desc()).all()]
    # Active loans đổi liên tục -> max_age ngắn
    return json_cache({"items": items, "count": len(items)}, max_age=15)

@app.post("/loans")
def borrow():
    data = request.get_json() or {}
    book_id, member_id = data.get("book_id"), data.get("member_id")
    days = int(data.get("days", 14))
    if not book_id or not member_id:
        return jsonify({"error": "book_id, member_id required"}), 400

    b = Book.query.get(book_id)
    if not b: return jsonify({"error": "Book not found"}), 404
    if b.stock <= 0: return jsonify({"error": "Out of stock"}), 409
    m = Member.query.get(member_id)
    if not m: return jsonify({"error": "Member not found"}), 404

    now = datetime.utcnow(); due = now + timedelta(days=days)
    b.stock -= 1
    l = Loan(book_id=book_id, member_id=member_id,
             borrowed_at=now.isoformat()+"Z", due_at=due.isoformat()+"Z")
    db.session.add(l); db.session.commit()
    return jsonify({
        "id": l.id, "book_id": l.book_id, "member_id": l.member_id,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    }), 201

@app.patch("/loans/<int:loan_id>")
def return_loan(loan_id):
    l = Loan.query.get(loan_id)
    if not l: return jsonify({"error":"Loan not found"}), 404
    data = request.get_json() or {}
    if data.get("returned") is True:
        if l.returned_at: return jsonify({"error":"Already returned"}), 409
        l.returned_at = datetime.utcnow().isoformat()+"Z"
        b = Book.query.get(l.book_id); b.stock += 1
        db.session.commit()
    return jsonify({
        "id": l.id, "book_id": l.book_id, "member_id": l.member_id,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    })

# ===== Docs (tùy chọn) =====
@app.get("/openapi.yaml")
def openapi_yaml():
    return send_from_directory(".", "openapi.yaml", mimetype="text/yaml")

SWAGGER_URL = "/docs"
API_URL = "/openapi.yaml"
swaggerui_bp = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={"app_name": "Library API"})
app.register_blueprint(swaggerui_bp, url_prefix=SWAGGER_URL)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
