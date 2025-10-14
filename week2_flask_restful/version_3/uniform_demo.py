# uniform_demo.py
from datetime import datetime, timedelta
from dateutil import tz
from flask import Flask, request, jsonify, make_response, send_from_directory, url_for
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
def now_iso():
    return datetime.now(tz.UTC).isoformat()

def problem(status: int, title: str, detail: str, type_: str = "about:blank"):
    """RFC 7807 problem+json"""
    resp = jsonify({"type": type_, "title": title, "status": status, "detail": detail})
    resp.status_code = status
    resp.mimetype = "application/problem+json"
    return resp

def book_repr(b: Book):
    return {
        "id": b.id,
        "title": b.title,
        "author": b.author,
        "stock": b.stock,
        "links": {"self": url_for("get_book", book_id=b.id, _external=True)}
    }

def member_repr(m: Member):
    return {
        "id": m.id,
        "name": m.name,
        "email": m.email,
        "links": {"self": url_for("get_member", member_id=m.id, _external=True)}
    }

def loan_repr(l: Loan):
    return {
        "id": l.id,
        "borrowed_at": l.borrowed_at,
        "due_at": l.due_at,
        "returned_at": l.returned_at,
        "book": {"id": l.book_id, "title": l.book.title,
                 "links": {"self": url_for("get_book", book_id=l.book_id, _external=True)}},
        "member": {"id": l.member_id, "name": l.member.name,
                   "links": {"self": url_for("get_member", member_id=l.member_id, _external=True)}},
        "links": {
            "self": url_for("get_loan", loan_id=l.id, _external=True),
            "return": url_for("patch_loan", loan_id=l.id, _external=True)
        }
    }

# ===== Books =====
@app.get("/books")
def list_books():
    books = [book_repr(b) for b in Book.query.order_by(Book.id).all()]
    return jsonify({"items": books, "count": len(books)})

@app.post("/books")
def create_book():
    data = request.get_json() or {}
    for f in ("title", "author", "stock"):
        if f not in data:
            return problem(400, "Invalid request", f"'{f}' is required")
    try:
        stock = int(data["stock"])
    except Exception:
        return problem(400, "Invalid request", "'stock' must be integer")
    b = Book(title=data["title"], author=data["author"], stock=stock)
    db.session.add(b); db.session.commit()
    resp = jsonify(book_repr(b))
    resp.status_code = 201
    resp.headers["Location"] = url_for("get_book", book_id=b.id, _external=True)
    return resp

@app.get("/books/<int:book_id>")
def get_book(book_id):
    b = Book.query.get(book_id)
    if not b: return problem(404, "Not found", "Book does not exist")
    return jsonify(book_repr(b))

@app.put("/books/<int:book_id>")
def update_book(book_id):
    b = Book.query.get(book_id)
    if not b: return problem(404, "Not found", "Book does not exist")
    data = request.get_json() or {}
    for f in ("title", "author", "stock"):
        if f not in data:
            return problem(400, "Invalid request", f"'{f}' is required")
    try:
        b.title = data["title"]; b.author = data["author"]; b.stock = int(data["stock"])
    except Exception:
        return problem(400, "Invalid request", "'stock' must be integer")
    db.session.commit()
    return jsonify(book_repr(b))

@app.delete("/books/<int:book_id>")
def delete_book(book_id):
    b = Book.query.get(book_id)
    if not b: return problem(404, "Not found", "Book does not exist")
    db.session.delete(b); db.session.commit()
    return "", 204

# ===== Members =====
@app.get("/members")
def list_members():
    ms = [member_repr(m) for m in Member.query.order_by(Member.id.desc()).all()]
    return jsonify({"items": ms, "count": len(ms)})

@app.post("/members")
def create_member():
    data = request.get_json() or {}
    for f in ("name", "email"):
        if f not in data:
            return problem(400, "Invalid request", f"'{f}' is required")
    if Member.query.filter_by(email=data["email"]).first():
        return problem(409, "Conflict", "Email already exists")
    m = Member(name=data["name"], email=data["email"])
    db.session.add(m); db.session.commit()
    resp = jsonify(member_repr(m))
    resp.status_code = 201
    resp.headers["Location"] = url_for("get_member", member_id=m.id, _external=True)
    return resp

@app.get("/members/<int:member_id>")
def get_member(member_id):
    m = Member.query.get(member_id)
    if not m: return problem(404, "Not found", "Member does not exist")
    return jsonify(member_repr(m))

@app.put("/members/<int:member_id>")
def update_member(member_id):
    m = Member.query.get(member_id)
    if not m: return problem(404, "Not found", "Member does not exist")
    data = request.get_json() or {}
    for f in ("name", "email"):
        if f not in data:
            return problem(400, "Invalid request", f"'{f}' is required")
    if Member.query.filter(Member.email == data["email"], Member.id != member_id).first():
        return problem(409, "Conflict", "Email already exists")
    m.name = data["name"]; m.email = data["email"]
    db.session.commit()
    return jsonify(member_repr(m))

@app.delete("/members/<int:member_id>")
def delete_member(member_id):
    m = Member.query.get(member_id)
    if not m: return problem(404, "Not found", "Member does not exist")
    db.session.delete(m); db.session.commit()
    return "", 204

@app.get("/members/<int:member_id>/details")
def member_details(member_id):
    status = request.args.get("status", "active")
    m = Member.query.get(member_id)
    if not m: return problem(404, "Not found", "Member does not exist")
    q = Loan.query.filter(Loan.member_id == member_id).join(Book)
    if status == "active":
        q = q.filter(Loan.returned_at.is_(None))
    elif status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    loans = [loan_repr(l) for l in q.order_by(Loan.id.desc()).all()]
    out = member_repr(m)
    out["loans"] = loans
    return jsonify(out)

# ===== Loans (Uniform) =====
@app.get("/loans")
def list_loans():
    status = request.args.get("status", "active")
    q = Loan.query
    if status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    elif status == "active":
        q = q.filter(Loan.returned_at.is_(None))
    loans = [loan_repr(l) for l in q.order_by(Loan.id.desc()).all()]
    return jsonify({"items": loans, "count": len(loans)})

@app.get("/loans/<int:loan_id>")
def get_loan(loan_id):
    l = Loan.query.get(loan_id)
    if not l: return problem(404, "Not found", "Loan does not exist")
    return jsonify(loan_repr(l))

@app.post("/loans")
def create_loan():
    data = request.get_json() or {}
    book_id, member_id = data.get("book_id"), data.get("member_id")
    days = int(data.get("days", 14))
    if not book_id or not member_id:
        return problem(400, "Invalid request", "'book_id' and 'member_id' are required")
    b = Book.query.get(book_id)
    if not b: return problem(404, "Not found", "Book not found")
    if b.stock <= 0: return problem(409, "Conflict", "Out of stock")
    m = Member.query.get(member_id)
    if not m: return problem(404, "Not found", "Member not found")

    now = datetime.utcnow(); due = now + timedelta(days=days)
    b.stock -= 1
    l = Loan(book_id=book_id, member_id=member_id,
             borrowed_at=now.isoformat()+"Z", due_at=due.isoformat()+"Z")
    db.session.add(l); db.session.commit()
    resp = jsonify(loan_repr(l))
    resp.status_code = 201
    resp.headers["Location"] = url_for("get_loan", loan_id=l.id, _external=True)
    return resp

@app.patch("/loans/<int:loan_id>")
def patch_loan(loan_id):
    l = Loan.query.get(loan_id)
    if not l: return problem(404, "Not found", "Loan does not exist")
    data = request.get_json() or {}
    if data.get("returned") is True:
        if l.returned_at:
            return problem(409, "Conflict", "Loan already returned")
        l.returned_at = datetime.utcnow().isoformat()+"Z"
        b = Book.query.get(l.book_id); b.stock += 1
        db.session.commit()
    return jsonify(loan_repr(l))

# ===== Docs (tuỳ chọn) =====
@app.get("/openapi.yaml")
def openapi_yaml():
    return send_from_directory(".", "openapi.yaml", mimetype="text/yaml")

SWAGGER_URL = "/docs"
API_URL = "/openapi.yaml"
swaggerui_bp = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={"app_name": "Library API"})
app.register_blueprint(swaggerui_bp, url_prefix=SWAGGER_URL)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
