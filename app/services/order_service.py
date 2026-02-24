"""Order business logic."""
from decimal import Decimal
from datetime import date
from app import db
from app.models import Order, OrderItem, Product
from app.services.numbering_service import NumberingService
from app.services.audit_service import AuditService


class OrderService:
    @staticmethod
    def create_order(customer_name, phone, email, items_data, discount=0, tax=0,
                    payment_method=None, payment_status='pending', order_status='pending',
                    notes=None, created_by_id=None):
        order_number = NumberingService.next_order_number()
        order = Order(
            order_number=order_number,
            customer_name=customer_name,
            phone=phone or None,
            email=email or None,
            order_date=date.today(),
            discount=Decimal(str(discount)),
            tax=Decimal(str(tax)),
            payment_method=payment_method,
            payment_status=payment_status,
            order_status=order_status,
            delivery_status='pending',
            notes=notes,
            created_by_id=created_by_id,
        )
        db.session.add(order)
        db.session.flush()

        total = Decimal('0')
        for item in items_data:
            qty = int(item.get('quantity', 0))
            price = Decimal(str(item.get('selling_price', 0)))
            subtotal = qty * price
            total += subtotal
            product_id = item.get('product_id') or None
            is_manual = item.get('item_type') == 'manual_entry' or not product_id
            buying = Decimal('0')
            if product_id:
                p = Product.query.get(product_id)
                if p:
                    buying = p.buying_price if p.buying_price is not None else Decimal('0')
                    p.stock_quantity -= qty
                    if p.stock_quantity < 0:
                        db.session.rollback()
                        raise ValueError(f"Insufficient stock for {p.name}")

            oi = OrderItem(
                order_id=order.id,
                product_id=product_id,
                item_type=item.get('item_type', 'manual_entry'),
                product_name=item.get('product_name', ''),
                buying_price=buying,
                selling_price=price,
                quantity=qty,
                subtotal=subtotal,
                is_manual_entry=is_manual,
            )
            db.session.add(oi)

        order.total_amount = total
        tax_amount = total * (Decimal(str(tax)) / 100) if tax else Decimal('0')
        order.tax = tax_amount
        order.grand_total = total - order.discount + tax_amount
        db.session.commit()
        AuditService.log('order.create', 'Order', order.id, order_number, created_by_id)
        return order

    @staticmethod
    def get_order_with_items(order_id):
        return Order.query.get_or_404(order_id)
