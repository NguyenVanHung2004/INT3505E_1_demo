# mongo_models.py
from mongoengine import Document, StringField

class AuditLog(Document):
    meta = {"collection": "audit_logs"}
    action = StringField(required=True)
    created_at = StringField(required=True)
