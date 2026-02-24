"""Dashboard routes."""
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func

from flask import render_template
from flask_login import login_required

from app import db
from app.blueprints.dashboard import dashboard_bp
from app.models import Product, Order, Delivery
from app.services import ProductService


@dashboard_bp.route('/')
@login_required
def index():
    today = datetime.utcnow().date()
    total_products = Product.query.filter_by(is_active=True).count()
    today_orders = Order.query.filter(Order.order_date == today, Order.order_status != 'cancelled').count()
    pending_deliveries = Delivery.query.filter(Delivery.status.in_(['pending', 'assigned', 'in_transit'])).count()
    low_stock = ProductService.get_low_stock_products()
    low_stock_count = len(low_stock)
    today_revenue = db.session.query(func.coalesce(func.sum(Order.grand_total), 0)).filter(
        Order.order_date == today,
        Order.order_status != 'cancelled',
        Order.payment_status == 'paid',
    ).scalar() or Decimal('0')

    # Last 30 days sales trend
    start_date = today - timedelta(days=30)
    sales_trend = (
        db.session.query(Order.order_date, func.sum(Order.grand_total).label('total'))
        .filter(
            Order.order_date >= start_date,
            Order.order_date <= today,
            Order.order_status != 'cancelled',
        )
        .group_by(Order.order_date)
        .order_by(Order.order_date)
        .all()
    )
    trend_labels = [d.strftime('%Y-%m-%d') for d, _ in sales_trend]
    trend_data = [float(t) for _, t in sales_trend]

    # Top selling products (from order items)
    from app.models import OrderItem
    top_products = (
        db.session.query(OrderItem.product_name, func.sum(OrderItem.quantity).label('qty'))
        .join(Order)
        .filter(Order.order_status != 'cancelled', Order.order_date >= start_date)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
        .all()
    )
    top_product_names = [p[0] for p in top_products]
    top_product_qty = [p[1] for p in top_products]

    # Payment status distribution
    payment_counts = (
        db.session.query(Order.payment_status, func.count(Order.id))
        .filter(Order.order_date >= start_date)
        .group_by(Order.payment_status)
        .all()
    )
    payment_labels = [p[0] for p in payment_counts]
    payment_data = [p[1] for p in payment_counts]

    recent_orders = (
        Order.query.filter(Order.order_status != 'cancelled')
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'dashboard/index.html',
        total_products=total_products,
        today_orders=today_orders,
        pending_deliveries=pending_deliveries,
        low_stock_count=low_stock_count,
        low_stock_products=low_stock[:5],
        today_revenue=today_revenue,
        trend_labels=trend_labels,
        trend_data=trend_data,
        top_product_names=top_product_names,
        top_product_qty=top_product_qty,
        payment_labels=payment_labels,
        payment_data=payment_data,
        recent_orders=recent_orders,
    )
