"""Delivery and DeliveryItem models."""
import uuid
from datetime import datetime
from decimal import Decimal

from app import db


class Delivery(db.Model):
    __tablename__ = 'deliveries'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    delivery_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=True)
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    delivery_address = db.Column(db.Text, nullable=False)
    delivery_date = db.Column(db.DateTime, nullable=True)
    scheduled_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    delivery_notes = db.Column(db.Text, nullable=True)
    items_description = db.Column(db.Text, nullable=True)
    assigned_to_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('DeliveryItem', backref='delivery', lazy='dynamic', cascade='all, delete-orphan')

    STATUSES = ['pending', 'assigned', 'in_transit', 'delivered', 'failed', 'cancelled']

    def __repr__(self):
        return f'<Delivery {self.delivery_number}>'


class DeliveryItem(db.Model):
    __tablename__ = 'delivery_items'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    delivery_id = db.Column(db.String(36), db.ForeignKey('deliveries.id'), nullable=False)
    order_item_id = db.Column(db.String(36), db.ForeignKey('order_items.id'), nullable=True)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    def __repr__(self):
        return f'<DeliveryItem {self.product_name} x {self.quantity}>'
