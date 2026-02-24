"""Delivery business logic."""
from datetime import date, datetime
from decimal import Decimal
from app import db
from app.models import Delivery, DeliveryItem, Order, OrderItem
from app.services.numbering_service import NumberingService
from app.services.audit_service import AuditService


class DeliveryService:
    @staticmethod
    def create_from_order(order_id, customer_name, phone, delivery_address,
                          scheduled_date=None, assigned_to_id=None, notes=None, item_quantities=None):
        order = Order.query.get_or_404(order_id)
        delivery_number = NumberingService.next_delivery_number()
        delivery = Delivery(
            delivery_number=delivery_number,
            order_id=order.id,
            customer_name=customer_name or order.customer_name,
            phone=phone or order.phone,
            delivery_address=delivery_address,
            scheduled_date=scheduled_date,
            status='pending',
            delivery_notes=notes,
            assigned_to_id=assigned_to_id,
        )
        db.session.add(delivery)
        db.session.flush()
        item_quantities = item_quantities or {}
        for oi in order.items:
            qty = item_quantities.get(oi.id, oi.quantity)
            if qty <= 0:
                continue
            di = DeliveryItem(
                delivery_id=delivery.id,
                order_item_id=oi.id,
                product_name=oi.product_name,
                quantity=min(int(qty), oi.quantity),
                unit_price=oi.selling_price,
            )
            db.session.add(di)
        order.delivery_status = 'assigned'
        db.session.commit()
        AuditService.log('delivery.create', 'Delivery', delivery.id, delivery_number)
        return delivery

    @staticmethod
    def create_standalone(customer_name, phone, delivery_address, items_data,
                          scheduled_date=None, assigned_to_id=None, notes=None):
        delivery_number = NumberingService.next_delivery_number()
        delivery = Delivery(
            delivery_number=delivery_number,
            order_id=None,
            customer_name=customer_name,
            phone=phone,
            delivery_address=delivery_address,
            scheduled_date=scheduled_date,
            status='pending',
            delivery_notes=notes,
            assigned_to_id=assigned_to_id,
        )
        db.session.add(delivery)
        db.session.flush()
        for item in items_data:
            di = DeliveryItem(
                delivery_id=delivery.id,
                product_name=item.get('product_name', ''),
                quantity=int(item.get('quantity', 0)),
                unit_price=Decimal(str(item.get('unit_price', 0))),
            )
            db.session.add(di)
        db.session.commit()
        AuditService.log('delivery.create', 'Delivery', delivery.id, delivery_number)
        return delivery
