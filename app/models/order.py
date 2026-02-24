"""Order and OrderItem models."""
import uuid
from datetime import datetime, date
from decimal import Decimal

from app import db


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    order_date = db.Column(db.Date, nullable=False, default=date.today)
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    discount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    tax = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    grand_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    payment_status = db.Column(db.String(20), default='pending', nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    order_status = db.Column(db.String(20), default='pending', nullable=False)
    delivery_status = db.Column(db.String(20), default='pending', nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    deliveries = db.relationship('Delivery', backref='order', lazy='dynamic', foreign_keys='Delivery.order_id')

    PAYMENT_STATUSES = ['pending', 'paid', 'partial', 'cancelled']
    ORDER_STATUSES = ['pending', 'processing', 'completed', 'cancelled']
    DELIVERY_STATUSES = ['pending', 'assigned', 'in_transit', 'delivered', 'failed', 'cancelled']

    def __repr__(self):
        return f'<Order {self.order_number}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=True)
    item_type = db.Column(db.String(20), nullable=False, default='existing_product')
    product_name = db.Column(db.String(200), nullable=False)
    buying_price = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    is_manual_entry = db.Column(db.Boolean, default=False, nullable=False)

    delivery_items = db.relationship('DeliveryItem', backref='order_item', lazy='dynamic', foreign_keys='DeliveryItem.order_item_id')

    def __repr__(self):
        return f'<OrderItem {self.product_name} x {self.quantity}>'
