"""Quotation and QuotationItem models."""
import uuid
from datetime import datetime
from decimal import Decimal

from app import db


class Quotation(db.Model):
    __tablename__ = 'quotations'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    quotation_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    discount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    tax = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    grand_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    status = db.Column(db.String(20), default='draft', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('QuotationItem', backref='quotation', lazy='dynamic', cascade='all, delete-orphan')

    STATUSES = ['draft', 'sent', 'accepted', 'expired', 'cancelled']

    def __repr__(self):
        return f'<Quotation {self.quotation_number}>'


class QuotationItem(db.Model):
    __tablename__ = 'quotation_items'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    quotation_id = db.Column(db.String(36), db.ForeignKey('quotations.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=True)
    item_type = db.Column(db.String(20), nullable=False, default='existing_product')
    product_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    is_manual_entry = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<QuotationItem {self.product_name} x {self.quantity}>'
