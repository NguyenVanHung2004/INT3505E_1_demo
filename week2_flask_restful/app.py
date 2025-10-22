#python -m venv .venv
#.venv\Scripts\activate
#pip install -r requirements.txt
#python app.py
# api at: http://127.0.0.1:5000/docs
from datetime import datetime, timedelta
from dateutil import tz
from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger, swag_from
from flask import send_from_directory
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///library.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --- Models ---
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

def now_iso():
    return datetime.now(tz.UTC).isoformat()

# --- Books ---
@app.get("/books")
def list_books():
    books = [{"id": b.id, "title": b.title} for b in Book.query.all()]
    resp = make_response(jsonify(books), 200)
    resp.headers["Cache-Control"] = "public, max-age=60"
    return jsonify({
    "status": "success",
    "data": books,
    "count": len(books)
}), 200

@app.post("/books")
def create_book():
    data = request.get_json() or {}
    for f in ("title","author","stock"):
        if f not in data: return jsonify({"error": f"{f} required"}), 400
    b = Book(title=data["title"], author=data["author"], stock=int(data["stock"]))
    db.session.add(b); db.session.commit()
    return jsonify({"id": b.id, "title": b.title, "author": b.author, "stock": b.stock}), 201

@app.get("/books/<int:book_id>")
def get_book(book_id):
    b = Book.query.get(book_id)
    if not b: return jsonify({"error":"Not found"}), 404
    return jsonify({"id": b.id, "title": b.title, "author": b.author, "stock": b.stock})

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

# --- Members ---
@app.get("/members")
def list_members():
    return jsonify([{"id": m.id, "name": m.name, "email": m.email} for m in Member.query.order_by(Member.id.desc()).all()])

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
    return jsonify({"id": m.id, "name": m.name, "email": m.email})

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

@app.get("/members/<int:member_id>/details")
def member_details(member_id):
    status = request.args.get("status", "active")  # active | returned | all

    m = Member.query.get(member_id)
    if not m:
        return jsonify({"error": "Not found"}), 404

    q = Loan.query.filter(Loan.member_id == member_id).join(Book)
    if status == "active":
        q = q.filter(Loan.returned_at.is_(None))
    elif status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    # else "all" -> không lọc

    loans = q.order_by(Loan.id.desc()).all()

    return jsonify({
        "id": m.id,
        "name": m.name,
        "email": m.email,
        "loans": [{
            "loan_id": l.id,
            "book_id": l.book_id,
            "book_title": l.book.title,
            "borrowed_at": l.borrowed_at,
            "due_at": l.due_at,
            "returned_at": l.returned_at
        } for l in loans]
    })

# --- Loans ---
@app.get("/loans")
def list_loans():
    status = request.args.get("status","active")
    q = Loan.query
    if status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    else:
        q = q.filter(Loan.returned_at.is_(None))
    loans = q.order_by(Loan.id.desc()).all()
    return jsonify([{
        "id": l.id,
        "book_id": l.book_id, "book_title": l.book.title,
        "member_id": l.member_id, "member_name": l.member.name,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    } for l in loans])

@app.post("/loans/borrow")
def borrow():
    data = request.get_json() or {}
    book_id, member_id = data.get("book_id"), data.get("member_id")
    days = int(data.get("days", 14))
    if not book_id or not member_id:
        return jsonify({"error": "book_id, member_id required"}), 400

    b = Book.query.get(book_id)
    if not b: return jsonify({"error": "Book not found"}), 404
    if b.stock <= 0: return jsonify({"error": "Out of stock"}), 400
    m = Member.query.get(member_id)
    if not m: return jsonify({"error": "Member not found"}), 404

    now = datetime.utcnow()
    due = now + timedelta(days=days)

    b.stock -= 1
    l = Loan(book_id=book_id, member_id=member_id,
             borrowed_at=now.isoformat()+"Z", due_at=due.isoformat()+"Z")
    db.session.add(l); db.session.commit()
    return jsonify({"id": l.id, "book_id": l.book_id, "member_id": l.member_id,
                    "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at}), 201

@app.post("/loans/return")
def return_loan():
    data = request.get_json() or {}
    loan_id = data.get("loan_id")
    if not loan_id: return jsonify({"error":"loan_id required"}), 400
    l = Loan.query.get(loan_id)
    if not l: return jsonify({"error":"Loan not found"}), 404
    if l.returned_at: return jsonify({"error":"Already returned"}), 400

    l.returned_at = datetime.utcnow().isoformat()+"Z"
    b = Book.query.get(l.book_id)
    b.stock += 1
    db.session.commit()
    return jsonify({
        "id": l.id, "book_id": l.book_id, "member_id": l.member_id,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    })

@app.get("/openapi.yaml")
def openapi_yaml():
    return send_from_directory(".", "openapi.yaml", mimetype="text/yaml")

@app.get("/redoc")
def redoc():
    return """
    <!doctype html>
    <html>
      <head><title>Library API Docs</title></head>
      <body>
        <redoc spec-url='/openapi.yaml'></redoc>
        <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
      </body>
    </html>
    """
SWAGGER_URL = "/docs"          # nơi mở UI
API_URL = "/openapi.yaml"      # file OpenAPI của bạn
swaggerui_bp = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Library API"}  # optional
)
app.register_blueprint(swaggerui_bp, url_prefix=SWAGGER_URL)
if __name__ == "__main__":
    app.run(debug=True, port=5000)
