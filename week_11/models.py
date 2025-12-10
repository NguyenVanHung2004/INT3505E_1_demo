from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    # Status: AVAILABLE, BORROWED
    status = db.Column(db.String(20), default='AVAILABLE') 
    loans = db.relationship('Loan', backref='book', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "status": self.status
        }

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    loans = db.relationship('Loan', backref='member', lazy=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email}

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    loan_date = db.Column(db.String(20), default=datetime.utcnow().strftime('%Y-%m-%d'))
    return_date = db.Column(db.String(20), nullable=True) # None = chưa trả

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "member_id": self.member_id,
            "loan_date": self.loan_date,
            "return_date": self.return_date,
            "status": "RETURNED" if self.return_date else "ACTIVE"
        }