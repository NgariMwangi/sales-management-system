"""Report routes."""
from datetime import datetime, timedelta
from io import BytesIO
from decimal import Decimal
from sqlalchemy import func

from flask import render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required

from app import db
from app.blueprints.reports import reports_bp
from app.decorators import reports_required
from app.forms import ReportFilterForm
from app.models import Order, OrderItem, Product, Delivery


@reports_bp.route('/', methods=['GET', 'POST'])
@login_required
@reports_required
def index():
    form = ReportFilterForm()
    date_from = request.args.get('date_from') or (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = request.args.get('date_to') or datetime.utcnow().strftime('%Y-%m-%d')
    report_type = request.args.get('report_type', 'sales')
    export = request.args.get('format', 'html')
    if form.validate_on_submit():
        date_from = form.date_from.data.strftime('%Y-%m-%d') if form.date_from.data else date_from
        date_to = form.date_to.data.strftime('%Y-%m-%d') if form.date_to.data else date_to
        report_type = form.report_type.data
        export = form.format.data or 'html'
        return redirect(url_for('reports.index', date_from=date_from, date_to=date_to, report_type=report_type, format=export))
    form.report_type.data = report_type
    form.format.data = export
    try:
        df = datetime.strptime(date_from, '%Y-%m-%d').date()
        dt = datetime.strptime(date_to, '%Y-%m-%d').date()
        form.date_from.data = df
        form.date_to.data = dt
    except Exception:
        df = datetime.utcnow().date() - timedelta(days=30)
        dt = datetime.utcnow().date()
        form.date_from.data = df
        form.date_to.data = dt
    if report_type == 'sales':
        data = _sales_report(df, dt)
        template = 'reports/sales.html'
    elif report_type == 'product_performance':
        data = _product_performance_report(df, dt)
        template = 'reports/product_performance.html'
    elif report_type == 'delivery_performance':
        data = _delivery_performance_report(df, dt)
        template = 'reports/delivery_performance.html'
    else:
        data = _stock_report()
        template = 'reports/stock.html'
    if export == 'pdf':
        return _export_pdf(template, data, date_from, date_to, report_type)
    if export == 'excel':
        return _export_excel(report_type, data, date_from, date_to)
    return render_template(template, form=form, data=data, date_from=date_from, date_to=date_to)


def _sales_report(date_from, date_to):
    orders = Order.query.filter(
        Order.order_date >= date_from,
        Order.order_date <= date_to,
        Order.order_status != 'cancelled',
    ).order_by(Order.order_date).all()
    total_revenue = sum(o.grand_total for o in orders)
    return {'orders': orders, 'total_revenue': total_revenue, 'count': len(orders)}


def _product_performance_report(date_from, date_to):
    rows = (
        db.session.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label('qty'),
            func.sum(OrderItem.subtotal).label('revenue'),
            func.sum((OrderItem.selling_price - OrderItem.buying_price) * OrderItem.quantity).label('profit'),
        )
        .join(Order)
        .filter(
            Order.order_date >= date_from,
            Order.order_date <= date_to,
            Order.order_status != 'cancelled',
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.subtotal).desc())
        .all()
    )
    return {'rows': rows}


def _delivery_performance_report(date_from, date_to):
    from datetime import time
    dt_from = datetime.combine(date_from, time.min)
    dt_to = datetime.combine(date_to, time.max)
    deliveries = Delivery.query.filter(
        Delivery.created_at >= dt_from,
        Delivery.created_at <= dt_to,
    ).all()
    total = len(deliveries)
    delivered = sum(1 for d in deliveries if d.status == 'delivered')
    return {'deliveries': deliveries, 'total': total, 'delivered': delivered, 'rate': (delivered / total * 100) if total else 0}


def _stock_report():
    products = Product.query.filter_by(is_active=True).order_by(Product.stock_quantity.asc()).all()
    low = [p for p in products if p.min_stock_level > 0 and p.stock_quantity <= p.min_stock_level]
    out = [p for p in products if p.stock_quantity <= 0]
    return {'products': products, 'low_stock': low, 'out_of_stock': out}


def _export_pdf(template, data, date_from, date_to, report_type):
    try:
        from weasyprint import HTML
        from flask import make_response
        html_content = render_template(template, data=data, date_from=date_from, date_to=date_to, print_mode=True)
        pdf_buffer = BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=f'report_{report_type}_{date_from}_{date_to}.pdf')
    except ImportError:
        flash('PDF export requires weasyprint. Use Excel or print from browser.', 'warning')
        return redirect(url_for('reports.index', date_from=date_from, date_to=date_to, report_type=report_type))


def _export_excel(report_type, data, date_from, date_to):
    try:
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Report'
        if report_type == 'sales' and 'orders' in data:
            ws.append(['Order', 'Date', 'Customer', 'Total'])
            for o in data['orders']:
                ws.append([o.order_number, str(o.order_date), o.customer_name, float(o.grand_total)])
        elif report_type == 'stock' and 'products' in data:
            ws.append(['Product', 'SKU', 'Stock', 'Min Level'])
            for p in data['products']:
                ws.append([p.name, p.sku or '', p.stock_quantity, p.min_stock_level])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f'report_{report_type}_{date_from}_{date_to}.xlsx')
    except ImportError:
        flash('Excel export requires openpyxl.', 'warning')
        return redirect(url_for('reports.index', date_from=date_from, date_to=date_to, report_type=report_type))
