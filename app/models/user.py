"""User model."""
import uuid
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='sales')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders_created = db.relationship('Order', backref='created_by_user', foreign_keys='Order.created_by_id')
    deliveries_assigned = db.relationship('Delivery', backref='assigned_to_user', foreign_keys='Delivery.assigned_to_id')

    ROLES = ['admin', 'manager', 'sales', 'delivery']

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles

    def is_admin(self):
        return self.role == 'admin'

    def can_manage_users(self):
        return self.role == 'admin'

    def can_manage_orders(self):
        return self.role in ('admin', 'manager', 'sales')

    def can_manage_deliveries(self):
        return self.role in ('admin', 'manager', 'delivery', 'sales')

    def can_view_reports(self):
        return self.role in ('admin', 'manager', 'sales')

    def can_manage_settings(self):
        return self.role in ('admin', 'manager')

    def __repr__(self):
        return f'<User {self.username}>'
