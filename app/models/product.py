"""Product model."""
import uuid
from datetime import datetime
from decimal import Decimal

from app import db


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False, index=True)
    sku = db.Column(db.String(80), unique=True, nullable=True, index=True)
    buying_price = db.Column(db.Numeric(12, 2), nullable=True)
    selling_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    category_id = db.Column(db.String(36), db.ForeignKey('categories.id'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    min_stock_level = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic', foreign_keys='OrderItem.product_id')

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock_level and self.min_stock_level > 0

    @property
    def is_out_of_stock(self):
        return self.stock_quantity <= 0

    @property
    def profit_margin(self):
        if self.selling_price is None:
            return None
        if self.buying_price is not None and float(self.buying_price) > 0:
            return float(self.selling_price) - float(self.buying_price)
        return float(self.selling_price)

    @property
    def profit_margin_percent(self):
        if self.selling_price is None or self.buying_price is None or float(self.buying_price) <= 0:
            return None
        return round((float(self.selling_price) - float(self.buying_price)) / float(self.buying_price) * 100, 2)

    def __repr__(self):
        return f'<Product {self.name}>'
