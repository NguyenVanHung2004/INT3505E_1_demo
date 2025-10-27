# python -m venv .venv
# .venv\Scripts\activate
# pip install -r requirements.txt
# python app.py
# Docs: http://127.0.0.1:5000/docs  (OpenAPI v1 ở /openapi.yaml)

#GET /api/v1/books?page=2&per_page=20&sort=title&order=asc
#GET /api/v1/members?pagination=offset&offset=40&limit=20
#GET /api/v1/loans?pagination=cursor&first=10
#GET /api/v1/loans?pagination=cursor&first=10&after=eyJsYXN0X2lkIjogMTAwfQ==
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, make_response, Blueprint, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
import base64, json, re

# -----------------------------
# App & Config
# -----------------------------
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///library.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -----------------------------
# Helpers (Consistency)
# -----------------------------
def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def envelope(data=None, status="success", meta=None, error=None, http_code=200, cache_max_age=None):
    body = {"status": status, "data": data, "meta": meta or {}, "error": error}
    resp = make_response(jsonify(body), http_code)
    if cache_max_age is not None:
        resp.headers["Cache-Control"] = f"public, max-age={cache_max_age}"
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp

def require_fields(payload, fields):
    missing = [f for f in fields if f not in payload or (isinstance(payload[f], str) and payload[f].strip() == "")]
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    return None

# ---------- Pagination strategies ----------
# page-based:   ?pagination=page&page=1&per_page=10
# offset-based: ?pagination=offset&offset=0&limit=10
# cursor-based: ?pagination=cursor&first=10&after=<opaque_cursor>
#
# Cursor là chuỗi base64(json) chứa {"last_id": <int>} để đảm bảo opaque và ổn định
def b64e(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()

def b64d(s: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(s.encode()).decode())
    except Exception:
        return {}

def parse_pagination_mode():
    mode = (request.args.get("pagination") or "page").lower()
    if mode not in ("page", "offset", "cursor"):
        mode = "page"
    return mode

def paginate_sqlalchemy(query, model, default_per=10, max_per=100):
    """
    Trả về (items, meta, mode) theo chiến lược phân trang hiện tại.
    - Page-based: dùng paginate() của SQLAlchemy
    - Offset-based: dùng offset/limit raw
    - Cursor-based: dùng id>last_id, order asc
    """
    mode = parse_pagination_mode()

    if mode == "page":
        page = max(int(request.args.get("page", 1)), 1)
        per_page = max(1, min(int(request.args.get("per_page", default_per)), max_per))
        pager = query.paginate(page=page, per_page=per_page, error_out=False)
        meta = {"pagination": "page", "page": page, "per_page": per_page, "total": pager.total, "pages": pager.pages}
        return pager.items, meta, mode

    if mode == "offset":
        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", default_per))
        except Exception:
            offset, limit = 0, default_per
        limit = max(1, min(limit, max_per))
        items = query.offset(max(0, offset)).limit(limit).all()
        # Nếu muốn total: cần .count() (tốn kém trên bảng lớn)
        meta = {"pagination": "offset", "offset": max(0, offset), "limit": limit, "count": len(items)}
        return items, meta, mode

    # cursor
    first = max(1, min(int(request.args.get("first", default_per)), max_per))
    after = request.args.get("after")
    last_id = 0
    if after:
        data = b64d(after)
        last_id = int(data.get("last_id", 0))

    # Cursor tăng dần theo id, đảm bảo ổn định và không trùng
    q2 = query.filter(getattr(model, "id") > last_id).order_by(getattr(model, "id").asc())
    items = q2.limit(first).all()
    next_cursor = None
    if items:
        next_cursor = b64e({"last_id": items[-1].id})
    meta = {"pagination": "cursor", "first": first, "next_cursor": next_cursor, "count": len(items)}
    return items, meta, mode

# ---------- Sorting ----------
def parse_sort(allowed_fields, default_field="id", default_dir="desc"):
    sort = request.args.get("sort", default_field)
    direction = request.args.get("order", default_dir).lower()
    direction = "desc" if direction not in ("asc", "desc") else direction
    if sort not in allowed_fields:
        sort = default_field
    return sort, direction

# -----------------------------
# Models
# -----------------------------
class Book(db.Model):
    __tablename__ = "book"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    author = db.Column(db.String, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.String, nullable=False, default=utc_now_iso)
    updated_at = db.Column(db.String, nullable=False, default=utc_now_iso)

class Member(db.Model):
    __tablename__ = "member"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    created_at = db.Column(db.String, nullable=False, default=utc_now_iso)
    updated_at = db.Column(db.String, nullable=False, default=utc_now_iso)

class Loan(db.Model):
    __tablename__ = "loan"
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

# -----------------------------
# API v1 Blueprint (Versioning)
# -----------------------------
api = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Health check
@api.get("/health-check")
def health_check():
    return envelope(data={"service": "library-api", "time": utc_now_iso()}, cache_max_age=15)

# -----------------------------
# Books (resource) + resource tree: /books/{id}/loans, /books/{id}/borrowers
# -----------------------------
@api.get("/books")
def list_books():
    # search + sort
    q = request.args.get("q", "").strip()
    sort_field, sort_dir = parse_sort({"id", "title", "author", "stock", "created_at", "updated_at"}, "id", "desc")
    query = Book.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Book.title.ilike(like), Book.author.ilike(like)))

    sort_col = getattr(Book, sort_field)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(sort_col)

    items, meta, mode = paginate_sqlalchemy(query, Book)
    data = [{
        "id": b.id, "title": b.title, "author": b.author, "stock": b.stock,
        "created_at": b.created_at, "updated_at": b.updated_at
    } for b in items]

    # Thêm hint query params vào meta (clarity)
    meta.update({"sort": sort_field, "order": sort_dir, "q": q or None})
    return envelope(data=data, meta=meta, cache_max_age=30)

@api.post("/books")
def create_book():
    payload = request.get_json() or {}
    err = require_fields(payload, ("title", "author", "stock"))
    if err: return envelope(status="error", error={"message": err}, http_code=400)
    try:
        stock = int(payload["stock"])
    except Exception:
        return envelope(status="error", error={"message": "stock must be integer"}, http_code=400)
    b = Book(title=payload["title"].strip(), author=payload["author"].strip(), stock=stock)
    db.session.add(b); db.session.commit()
    b.updated_at = utc_now_iso(); db.session.commit()
    return envelope(
        data={"id": b.id, "title": b.title, "author": b.author, "stock": b.stock,
              "created_at": b.created_at, "updated_at": b.updated_at},
        http_code=201
    )

@api.get("/books/<int:book_id>")
def get_book(book_id):
    b = Book.query.get(book_id)
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)
    return envelope(
        data={"id": b.id, "title": b.title, "author": b.author, "stock": b.stock,
              "created_at": b.created_at, "updated_at": b.updated_at},
        cache_max_age=60
    )

@api.put("/books/<int:book_id>")
def update_book(book_id):
    b = Book.query.get(book_id)
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)
    payload = request.get_json() or {}
    err = require_fields(payload, ("title", "author", "stock"))
    if err: return envelope(status="error", error={"message": err}, http_code=400)
    try:
        stock = int(payload["stock"])
    except Exception:
        return envelope(status="error", error={"message": "stock must be integer"}, http_code=400)
    b.title = payload["title"].strip()
    b.author = payload["author"].strip()
    b.stock = stock
    b.updated_at = utc_now_iso()
    db.session.commit()
    return envelope(
        data={"id": b.id, "title": b.title, "author": b.author, "stock": b.stock,
              "created_at": b.created_at, "updated_at": b.updated_at}
    )

@api.delete("/books/<int:book_id>")
def delete_book(book_id):
    b = Book.query.get(book_id)
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)
    db.session.delete(b); db.session.commit()
    return envelope(data=None, http_code=204)

# --- Resource tree: các loans của 1 book
@api.get("/books/<int:book_id>/loans")
def book_loans(book_id):
    b = Book.query.get(book_id)
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)

    status = request.args.get("status", "active")  # active|returned|all
    q = Loan.query.filter(Loan.book_id == book_id)
    if status == "active":
        q = q.filter(Loan.returned_at.is_(None))
    elif status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))

    # sort + phân trang (ba chiến lược)
    sort_field, sort_dir = parse_sort({"id", "borrowed_at", "due_at", "returned_at"}, "id", "desc")
    sort_col = getattr(Loan, sort_field)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    q = q.order_by(sort_col)

    items, meta, mode = paginate_sqlalchemy(q, Loan)
    data = [{
        "id": l.id,
        "book_id": l.book_id, "book_title": b.title,
        "member_id": l.member_id, "member_name": l.member.name,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    } for l in items]
    meta.update({"status": status, "sort": sort_field, "order": sort_dir})
    return envelope(data=data, meta=meta)

# --- Resource tree: danh sách người đã/đang mượn 1 book
@api.get("/books/<int:book_id>/borrowers")
def book_borrowers(book_id):
    b = Book.query.get(book_id)
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)

    # distinct members tham gia loan của book
    q = (db.session.query(Member)
         .join(Loan, Loan.member_id == Member.id)
         .filter(Loan.book_id == book_id)
         .distinct())

    # sắp xếp theo id member
    q = q.order_by(Member.id.asc())
    items, meta, mode = paginate_sqlalchemy(q, Member)
    data = [{"id": m.id, "name": m.name, "email": m.email} for m in items]
    meta.update({"book_id": book_id})
    return envelope(data=data, meta=meta)

# -----------------------------
# Members (resource) + resource tree: /members/{id}/loans
# -----------------------------
@api.get("/members")
def list_members():
    q = request.args.get("q", "").strip()
    sort_field, sort_dir = parse_sort({"id", "name", "email", "created_at"}, "id", "desc")
    query = Member.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Member.name.ilike(like), Member.email.ilike(like)))

    sort_col = getattr(Member, sort_field)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(sort_col)

    items, meta, mode = paginate_sqlalchemy(query, Member)
    data = [{"id": m.id, "name": m.name, "email": m.email,
             "created_at": m.created_at, "updated_at": m.updated_at} for m in items]
    meta.update({"sort": sort_field, "order": sort_dir, "q": q or None})
    return envelope(data=data, meta=meta, cache_max_age=15)

@api.post("/members")
def create_member():
    payload = request.get_json() or {}
    err = require_fields(payload, ("name", "email"))
    if err: return envelope(status="error", error={"message": err}, http_code=400)
    email = payload["email"].strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return envelope(status="error", error={"message": "email invalid"}, http_code=400)
    if Member.query.filter_by(email=email).first():
        return envelope(status="error", error={"message": "email already exists"}, http_code=409)

    m = Member(name=payload["name"].strip(), email=email)
    db.session.add(m); db.session.commit()
    m.updated_at = utc_now_iso(); db.session.commit()
    return envelope(
        data={"id": m.id, "name": m.name, "email": m.email,
              "created_at": m.created_at, "updated_at": m.updated_at},
        http_code=201
    )

@api.get("/members/<int:member_id>")
def get_member(member_id):
    m = Member.query.get(member_id)
    if not m:
        return envelope(status="error", error={"message": "Member not found"}, http_code=404)
    return envelope(
        data={"id": m.id, "name": m.name, "email": m.email,
              "created_at": m.created_at, "updated_at": m.updated_at},
        cache_max_age=60
    )

@api.put("/members/<int:member_id>")
def update_member(member_id):
    m = Member.query.get(member_id)
    if not m:
        return envelope(status="error", error={"message": "Member not found"}, http_code=404)
    payload = request.get_json() or {}
    err = require_fields(payload, ("name", "email"))
    if err: return envelope(status="error", error={"message": err}, http_code=400)
    email = payload["email"].strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return envelope(status="error", error={"message": "email invalid"}, http_code=400)
    if Member.query.filter(Member.email == email, Member.id != member_id).first():
        return envelope(status="error", error={"message": "email already exists"}, http_code=409)

    m.name = payload["name"].strip()
    m.email = email
    m.updated_at = utc_now_iso()
    db.session.commit()
    return envelope(
        data={"id": m.id, "name": m.name, "email": m.email,
              "created_at": m.created_at, "updated_at": m.updated_at}
    )

@api.delete("/members/<int:member_id>")
def delete_member(member_id):
    m = Member.query.get(member_id)
    if not m:
        return envelope(status="error", error={"message": "Member not found"}, http_code=404)
    db.session.delete(m); db.session.commit()
    return envelope(data=None, http_code=204)

@api.get("/members/<int:member_id>/loans")
def member_loans(member_id):
    # resource tree: loans thuộc về 1 member
    status = request.args.get("status", "active")  # active|returned|all
    m = Member.query.get(member_id)
    if not m:
        return envelope(status="error", error={"message": "Member not found"}, http_code=404)

    q = Loan.query.filter(Loan.member_id == member_id).join(Book)
    if status == "active":
        q = q.filter(Loan.returned_at.is_(None))
    elif status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))

    sort_field, sort_dir = parse_sort({"id", "borrowed_at", "due_at", "returned_at"}, "id", "desc")
    sort_col = getattr(Loan, sort_field)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    q = q.order_by(sort_col)

    items, meta, mode = paginate_sqlalchemy(q, Loan)
    data = [{
        "id": l.id,
        "book_id": l.book_id, "book_title": l.book.title,
        "member_id": l.member_id, "member_name": m.name,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    } for l in items]
    meta.update({"member_id": member_id, "status": status, "sort": sort_field, "order": sort_dir})
    return envelope(data=data, meta=meta)

# -----------------------------
# Loans (resource)
# -----------------------------
@api.get("/loans")
def list_loans():
    status = request.args.get("status", "active")  # active|returned
    q = Loan.query
    if status == "returned":
        q = q.filter(Loan.returned_at.isnot(None))
    elif status == "active":
        q = q.filter(Loan.returned_at.is_(None))

    sort_field, sort_dir = parse_sort({"id", "borrowed_at", "due_at", "returned_at"}, "id", "desc")
    sort_col = getattr(Loan, sort_field)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    q = q.order_by(sort_col)

    items, meta, mode = paginate_sqlalchemy(q, Loan)
    data = [{
        "id": l.id,
        "book_id": l.book_id, "book_title": l.book.title,
        "member_id": l.member_id, "member_name": l.member.name,
        "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at
    } for l in items]
    meta.update({"status": status, "sort": sort_field, "order": sort_dir})
    return envelope(data=data, meta=meta)

@api.post("/loans")
def create_loan():
    payload = request.get_json() or {}
    err = require_fields(payload, ("book_id", "member_id"))
    if err: return envelope(status="error", error={"message": err}, http_code=400)

    days = int(payload.get("days", 14))
    b = Book.query.get(payload["book_id"])
    if not b:
        return envelope(status="error", error={"message": "Book not found"}, http_code=404)
    if b.stock <= 0:
        return envelope(status="error", error={"message": "Out of stock"}, http_code=400)
    m = Member.query.get(payload["member_id"])
    if not m:
        return envelope(status="error", error={"message": "Member not found"}, http_code=404)

    now = datetime.utcnow()
    due = now + timedelta(days=days)
    b.stock -= 1
    l = Loan(book_id=b.id, member_id=m.id, borrowed_at=now.isoformat() + "Z", due_at=due.isoformat() + "Z")
    db.session.add(l); db.session.commit()

    return envelope(
        data={"id": l.id, "book_id": l.book_id, "member_id": l.member_id,
              "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at},
        http_code=201
    )

@api.patch("/loans/<int:loan_id>")
def return_loan(loan_id):
    l = Loan.query.get(loan_id)
    if not l:
        return envelope(status="error", error={"message": "Loan not found"}, http_code=404)
    if l.returned_at:
        return envelope(status="error", error={"message": "Already returned"}, http_code=400)

    payload = request.get_json(silent=True) or {}
    if "returned" in payload and not payload.get("returned"):
        return envelope(status="error", error={"message": "returned must be true"}, http_code=400)

    l.returned_at = datetime.utcnow().isoformat() + "Z"
    b = Book.query.get(l.book_id)
    b.stock += 1
    db.session.commit()
    return envelope(
        data={"id": l.id, "book_id": l.book_id, "member_id": l.member_id,
              "borrowed_at": l.borrowed_at, "due_at": l.due_at, "returned_at": l.returned_at}
    )

# -----------------------------
# OpenAPI & Docs (giữ nguyên đường dẫn)
# -----------------------------
@app.get("/openapi.yaml")
def openapi_yaml():
    return send_from_directory(".", "openapi.yaml", mimetype="text/yaml")

swaggerui_bp = get_swaggerui_blueprint("/docs", "/openapi.yaml", config={"app_name": "Library API"})
app.register_blueprint(swaggerui_bp, url_prefix="/docs")

# Mount API v1
app.register_blueprint(api)

# -----------------------------
# Error Handlers
# -----------------------------
@app.errorhandler(404)
def handle_404(e):
    return envelope(status="error", error={"message": "Not found"}, http_code=404)

@app.errorhandler(405)
def handle_405(e):
    return envelope(status="error", error={"message": "Method not allowed"}, http_code=405)

@app.errorhandler(500)
def handle_500(e):
    return envelope(status="error", error={"message": "Internal server error"}, http_code=500)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
