"""Application settings model."""
import uuid
from datetime import datetime

from app import db


class Setting(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        s = Setting.query.filter_by(key=key).first()
        return s.value if s else default

    @staticmethod
    def set(key, value, category=None):
        s = Setting.query.filter_by(key=key).first()
        if s:
            s.value = str(value) if value is not None else None
            s.category = category
        else:
            s = Setting(key=key, value=str(value) if value is not None else None, category=category)
            db.session.add(s)
        db.session.commit()
        return s

    def __repr__(self):
        return f'<Setting {self.key}>'
