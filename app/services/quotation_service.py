"""Quotation business logic and conversion to order."""
from decimal import Decimal
from datetime import date
from app import db
from app.models import Quotation, QuotationItem, Order, OrderItem, Product
from app.services.numbering_service import NumberingService
from app.services.order_service import OrderService
from app.services.audit_service import AuditService


class QuotationService:
    @staticmethod
    def create_quotation(customer_name, phone, email, valid_until, items_data,
                         discount=0, tax=0, status='draft', notes=None, created_by_id=None):
        quotation_number = NumberingService.next_quotation_number()
        quo = Quotation(
            quotation_number=quotation_number,
            customer_name=customer_name,
            phone=phone or None,
            email=email or None,
            valid_until=valid_until,
            discount=Decimal(str(discount)),
            tax=Decimal(str(tax)),
            status=status,
            notes=notes,
            created_by_id=created_by_id,
        )
        db.session.add(quo)
        db.session.flush()

        total = Decimal('0')
        for item in items_data:
            qty = int(item.get('quantity', 0))
            unit_price = Decimal(str(item.get('unit_price', 0)))
            disc_pct = Decimal(str(item.get('discount_percent', 0)))
            subtotal = qty * unit_price * (1 - disc_pct / 100)
            total += subtotal
            product_id = item.get('product_id') or None
            is_manual = item.get('item_type') == 'manual_entry' or not product_id

            qi = QuotationItem(
                quotation_id=quo.id,
                product_id=product_id,
                item_type=item.get('item_type', 'manual_entry'),
                product_name=item.get('product_name', ''),
                description=item.get('description'),
                quantity=qty,
                unit_price=unit_price,
                discount_percent=disc_pct,
                subtotal=subtotal,
                is_manual_entry=is_manual,
            )
            db.session.add(qi)

        quo.total_amount = total
        tax_amount = total * (Decimal(str(tax)) / 100) if tax else Decimal('0')
        quo.tax = tax_amount
        quo.grand_total = total - quo.discount + tax_amount
        db.session.commit()
        AuditService.log('quotation.create', 'Quotation', quo.id, quotation_number, created_by_id)
        return quo

    @staticmethod
    def update_quotation_items(quotation, items_data, discount=0, tax_percent=0):
        """Replace quotation line items and recompute totals. Does not commit."""
        for qi in list(quotation.items):
            db.session.delete(qi)
        total = Decimal('0')
        for item in items_data:
            qty = int(item.get('quantity', 0))
            unit_price = Decimal(str(item.get('unit_price', 0)))
            disc_pct = Decimal(str(item.get('discount_percent', 0)))
            subtotal = qty * unit_price * (1 - disc_pct / 100)
            total += subtotal
            product_id = item.get('product_id') or None
            is_manual = item.get('item_type') == 'manual_entry' or not product_id
            qi = QuotationItem(
                quotation_id=quotation.id,
                product_id=product_id,
                item_type=item.get('item_type', 'manual_entry'),
                product_name=item.get('product_name', ''),
                description=item.get('description'),
                quantity=qty,
                unit_price=unit_price,
                discount_percent=disc_pct,
                subtotal=subtotal,
                is_manual_entry=is_manual,
            )
            db.session.add(qi)
        quotation.total_amount = total
        quotation.discount = Decimal(str(discount))
        tax_amount = total * (Decimal(str(tax_percent)) / 100) if tax_percent else Decimal('0')
        quotation.tax = tax_amount
        quotation.grand_total = total - quotation.discount + tax_amount

    @staticmethod
    def convert_to_order(quotation_id, created_by_id=None):
        quo = Quotation.query.get_or_404(quotation_id)
        if quo.status != 'accepted':
            quo.status = 'accepted'
        items_data = []
        for qi in quo.items:
            price = qi.unit_price
            if qi.product_id:
                p = Product.query.get(qi.product_id)
                if p:
                    price = p.selling_price
            items_data.append({
                'item_type': 'manual_entry' if qi.is_manual_entry else 'existing_product',
                'product_id': qi.product_id,
                'product_name': qi.product_name,
                'quantity': qi.quantity,
                'selling_price': str(price),
            })
        order = OrderService.create_order(
            customer_name=quo.customer_name,
            phone=quo.phone,
            email=quo.email,
            items_data=items_data,
            discount=float(quo.discount),
            tax=float(quo.tax or 0),
            payment_method=None,
            payment_status='pending',
            order_status='pending',
            notes=f"Converted from quotation {quo.quotation_number}",
            created_by_id=created_by_id,
        )
        db.session.commit()
        AuditService.log('quotation.convert_to_order', 'Quotation', quo.id, order.order_number, created_by_id)
        return order
