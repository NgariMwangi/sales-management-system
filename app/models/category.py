"""Category model."""
import uuid
from datetime import datetime

from app import db


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', backref='category', lazy='dynamic', foreign_keys='Product.category_id')

    def __repr__(self):
        return f'<Category {self.name}>'
