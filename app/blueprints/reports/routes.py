"""Report routes."""
import os
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from flask import render_template, request, send_file, flash, redirect, url_for, current_app
from flask_login import login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageTemplate, Frame,
)
from sqlalchemy import func

from app import db
from app.blueprints.reports import reports_bp
from app.decorators import reports_required
from app.forms import ReportFilterForm
from app.models import Order, OrderItem, Product, Delivery
from app.pdf_fonts import register_pdf_fonts, get_pdf_fonts


def _hline(width_pt):
    """Thin horizontal line (grey), full width."""
    t = Table([['']], colWidths=[width_pt], rowHeights=[2])
    t.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_report_pdf(report_type, data, date_from, date_to):
    """Build report PDF with same format as invoice (logo, address, title, tables). Returns bytes."""
    buffer = BytesIO()
    margin = 50
    pw_pt, ph_pt = letter[0], letter[1]
    frame_width = pw_pt - 2 * margin
    frame_height = ph_pt - 2 * margin
    frame = Frame(
        margin, margin, frame_width, frame_height,
        id='normal',
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc = BaseDocTemplate(
        buffer, pagesize=letter,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
    )
    doc.addPageTemplates([PageTemplate(id='First', frames=[frame]), PageTemplate(id='Later', frames=[frame])])
    register_pdf_fonts(current_app.static_folder)
    fonts = get_pdf_fonts()
    styles = getSampleStyleSheet()
    black = colors.black
    grey = colors.HexColor('#555555')

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=20, spaceAfter=2, textColor=black, fontName=fonts['bold'], leftIndent=0, firstLineIndent=0,
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'], fontSize=10, textColor=grey, spaceAfter=0, leftIndent=0, firstLineIndent=0,
        rightIndent=0, bulletIndent=0, fontName=fonts['regular'],
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontSize=11, textColor=black, spaceAfter=2, leftIndent=0, firstLineIndent=0,
        fontName=fonts['regular'],
    )
    story = []

    # ----- Header: same as invoice (logo.png at half size + address) -----
    static_dir = current_app.static_folder
    logo_path = os.path.join(static_dir, 'logo.png')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = frame_width
                max_h_pt = 1.4 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                logo_img = Image(logo_path, width=pw * scale * 0.5, height=ph * scale * 0.5)
            else:
                logo_img = Image(logo_path, width=frame_width * 0.5, height=0.7 * inch)
            logo_img.hAlign = 'LEFT'
            story.append(logo_img)
        except Exception:
            pass
    story.append(Spacer(1, 0.15 * inch))
    addr_style = ParagraphStyle(
        'Addr', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#555555'),
        leftIndent=0, spaceAfter=0, spaceBefore=2, fontName=fonts['regular'],
    )
    story.append(Paragraph('Tel: 0725799182 | Gikomba, Kombo Munyiri Rd.', addr_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.15 * inch))

    # ----- Report title and date range -----
    titles = {
        'sales': 'SALES REPORT',
        'product_performance': 'PRODUCT PERFORMANCE REPORT',
        'delivery_performance': 'DELIVERY PERFORMANCE REPORT',
        'stock': 'STOCK REPORT',
    }
    story.append(Paragraph(titles.get(report_type, 'REPORT').upper(), title_style))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.12 * inch))
    ref_table = Table([
        [Paragraph('Date From: <b>{}</b>'.format(date_from), small_style),
         Paragraph('Date To: <b>{}</b>'.format(date_to), ParagraphStyle('SmallRight', parent=small_style, alignment=2))]
    ], colWidths=[frame_width - 2.5 * inch, 2.5 * inch])
    ref_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 0.2 * inch))

    # ----- Report-specific content -----
    if report_type == 'sales':
        story.append(Paragraph('Total Revenue: <b>{:,.2f}</b>  |  Orders: <b>{}</b>'.format(
            float(data.get('total_revenue') or 0), data.get('count', 0)), body_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(_hline(frame_width))
        story.append(Spacer(1, 0.12 * inch))
        tdata = [['Order #', 'Date', 'Customer', 'Total']]
        for o in data.get('orders') or []:
            tdata.append([
                o.order_number or '—',
                o.order_date.strftime('%d/%m/%Y') if o.order_date else '—',
                (o.customer_name or '—')[:40],
                '%.2f' % float(o.grand_total or 0),
            ])
        col_w = [1.2 * inch, 1.0 * inch, frame_width - 3.2 * inch, 1.0 * inch]
        t = Table(tdata, colWidths=col_w)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
            ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('LEFTPADDING', (0, 0), (0, -1), 8),
            ('LEFTPADDING', (1, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ]))
        story.append(t)
    elif report_type == 'product_performance':
        tdata = [['Product', 'Qty Sold', 'Revenue', 'Profit']]
        for r in data.get('rows') or []:
            tdata.append([
                (r.product_name or '—')[:50],
                str(r.qty or 0),
                '%.2f' % float(r.revenue or 0),
                '%.2f' % float(r.profit or 0) if r.profit is not None else '—',
            ])
        col_w = [frame_width - 2.8 * inch, 0.8 * inch, 1.0 * inch, 1.0 * inch]
        t = Table(tdata, colWidths=col_w)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
            ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('LEFTPADDING', (0, 0), (0, -1), 8),
            ('LEFTPADDING', (1, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ]))
        story.append(t)
    elif report_type == 'delivery_performance':
        total = data.get('total', 0)
        delivered = data.get('delivered', 0)
        rate = data.get('rate', 0)
        story.append(Paragraph('Total: <b>{}</b>  |  Delivered: <b>{}</b>  |  Success Rate: <b>{:.1f}%</b>'.format(
            total, delivered, rate), body_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(_hline(frame_width))
        story.append(Spacer(1, 0.12 * inch))
        tdata = [['Delivery #', 'Customer', 'Status', 'Date']]
        for d in data.get('deliveries') or []:
            tdata.append([
                d.delivery_number or '—',
                (d.customer_name or '—')[:35],
                (d.status or '—').replace('_', ' ').title(),
                d.created_at.strftime('%d/%m/%Y') if d.created_at else '—',
            ])
        col_w = [1.2 * inch, frame_width - 2.8 * inch, 1.0 * inch, 0.9 * inch]
        t = Table(tdata, colWidths=col_w)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
            ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('LEFTPADDING', (0, 0), (0, -1), 8),
            ('LEFTPADDING', (1, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
    else:
        # stock
        low_n = len(data.get('low_stock') or [])
        out_n = len(data.get('out_of_stock') or [])
        story.append(Paragraph('Low stock: <b>{}</b>  |  Out of stock: <b>{}</b>'.format(low_n, out_n), body_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(_hline(frame_width))
        story.append(Spacer(1, 0.12 * inch))
        tdata = [['Product', 'SKU', 'Stock', 'Min Level', 'Status']]
        for p in data.get('products') or []:
            status = 'Out' if (p.stock_quantity or 0) <= 0 else ('Low' if (p.min_stock_level or 0) > 0 and (p.stock_quantity or 0) <= (p.min_stock_level or 0) else 'OK')
            tdata.append([
                (p.name or '—')[:40],
                (p.sku or '—')[:15],
                str(p.stock_quantity or 0),
                str(p.min_stock_level or '—'),
                status,
            ])
        col_w = [frame_width - 2.6 * inch, 0.8 * inch, 0.6 * inch, 0.7 * inch, 0.5 * inch]
        t = Table(tdata, colWidths=col_w)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
            ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('LEFTPADDING', (0, 0), (0, -1), 8),
            ('LEFTPADDING', (1, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (2, 0), (4, -1), 'RIGHT'),
        ]))
        story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


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
    pdf_bytes = _build_report_pdf(report_type, data, date_from, date_to)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'report_{report_type}_{date_from}_{date_to}.pdf',
    )


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
