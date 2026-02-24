"""Order routes."""
import json
import os
from io import BytesIO

from flask import render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from app import db
from app.blueprints.orders import orders_bp
from app.decorators import role_required
from app.forms import OrderForm
from app.models import Order, Product
from app.services import OrderService


@orders_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    payment = request.args.get('payment', '')
    query = Order.query
    if status:
        query = query.filter(Order.order_status == status)
    if payment:
        query = query.filter(Order.payment_status == payment)
    orders = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('orders/list.html', orders=orders, status=status, payment=payment)


@orders_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def add():
    form = OrderForm()
    if form.validate_on_submit():
        items_raw = request.form.getlist('items')
        # items can be JSON array from frontend
        import json
        items_json = request.form.get('items_json', '[]')
        try:
            items_data = json.loads(items_json) if items_json else []
        except Exception:
            items_data = []
        if not items_data:
            flash('Add at least one item.', 'danger')
            return render_template('orders/form.html', form=form, title='New Order')
        try:
            order = OrderService.create_order(
                customer_name=form.customer_name.data,
                phone=form.phone.data,
                email=form.email.data,
                items_data=items_data,
                discount=float(form.discount.data or 0),
                tax=float(form.tax.data or 0),
                payment_method=form.payment_method.data,
                payment_status=form.payment_status.data,
                order_status=form.order_status.data,
                notes=form.notes.data,
                created_by_id=current_user.id,
            )
            flash('Order created.', 'success')
            return redirect(url_for('orders.detail', order_id=order.id))
        except ValueError as e:
            flash(str(e), 'danger')
    return render_template('orders/form.html', form=form, title='New Order')


@orders_bp.route('/<order_id>')
@login_required
def detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('orders/detail.html', order=order)


@orders_bp.route('/<order_id>/invoice')
@login_required
def invoice(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('orders/invoice.html', order=order)


def _build_order_invoice_pdf(order):
    """Build a professional invoice PDF for an order; returns bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor('#1e3a5f')
    slate = colors.HexColor('#334155')
    slate_light = colors.HexColor('#64748b')
    border_light = colors.HexColor('#e2e8f0')
    bg_row = colors.HexColor('#f8fafc')
    accent = colors.HexColor('#0f766e')

    title_style = ParagraphStyle(
        'InvoiceTitle', parent=styles['Heading1'],
        fontSize=22, spaceAfter=4, textColor=navy, fontName='Helvetica-Bold',
    )
    meta_style = ParagraphStyle(
        'InvoiceMeta', parent=styles['Normal'],
        fontSize=9, textColor=slate_light, spaceAfter=0,
    )
    section_style = ParagraphStyle(
        'SectionHead', parent=styles['Normal'],
        fontSize=9, textColor=slate, spaceAfter=4, fontName='Helvetica-Bold',
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontSize=10, textColor=slate, spaceAfter=2,
    )
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=8, textColor=slate_light,
        alignment=1, spaceBefore=24, spaceAfter=0,
    )
    story = []

    # Logo
    logo_path = os.path.join(current_app.static_folder, 'logo.jpg')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = 1.75 * inch
                max_h_pt = 1.25 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                img = Image(logo_path, width=pw * scale, height=ph * scale)
            else:
                img = Image(logo_path, width=1.75 * inch, height=1.25 * inch)
            story.append(img)
            story.append(Spacer(1, 0.15 * inch))
        except Exception:
            pass

    story.append(Paragraph('INVOICE', title_style))
    order_date = order.order_date.strftime('%d %b %Y') if order.order_date else '—'
    story.append(Paragraph(
        f'Order No. <b>{order.order_number}</b> &nbsp;·&nbsp; Date {order_date}',
        meta_style,
    ))
    story.append(Spacer(1, 0.35 * inch))

    story.append(Paragraph('BILL TO', section_style))
    story.append(Paragraph(order.customer_name or '—', body_style))
    if order.phone or order.email:
        parts = [p for p in (order.phone, order.email) if p]
        story.append(Paragraph(' · '.join(parts), meta_style))
    story.append(Spacer(1, 0.4 * inch))

    # Items table (Product, Qty, Unit Price, Subtotal)
    data = [['Product / Description', 'Qty', 'Unit Price', 'Subtotal']]
    for oi in order.items:
        data.append([
            oi.product_name or '—',
            str(oi.quantity),
            '%.2f' % float(oi.selling_price),
            '%.2f' % float(oi.subtotal),
        ])
    col_widths = [3.8 * inch, 0.7 * inch, 1.3 * inch, 1.3 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (0, 0), (0, 0), 12),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 12),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), slate),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 1), (0, -1), 12),
        ('RIGHTPADDING', (0, 1), (-1, -1), 12),
        ('LINEBELOW', (0, 0), (-1, 0), 0, colors.white),
        ('BOX', (0, 0), (-1, -1), 0.5, border_light),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, border_light),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, bg_row]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3 * inch))

    total = float(order.total_amount or 0)
    discount = float(order.discount or 0)
    tax = float(order.tax or 0)
    grand = float(order.grand_total or 0)
    totals_data = [['Subtotal', '%.2f' % total]]
    if discount != 0:
        totals_data.append(['Discount', '%.2f' % discount])
    if tax != 0:
        totals_data.append(['Tax', '%.2f' % tax])
    totals_data.append(['Grand Total', '%.2f' % grand])
    tot = Table(totals_data, colWidths=[1.6 * inch, 1.35 * inch])
    tot.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -2), 10),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('TEXTCOLOR', (0, 0), (-1, -2), slate),
        ('TEXTCOLOR', (0, -1), (-1, -1), navy),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdfa')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, accent),
        ('BOX', (0, 0), (-1, -1), 0.5, border_light),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, border_light),
    ]))
    story.append(tot)

    if order.notes:
        story.append(Spacer(1, 0.35 * inch))
        story.append(Paragraph('NOTES', section_style))
        story.append(Paragraph(order.notes.replace('\n', '<br/>'), body_style))

    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        'Thank you for your business. If you have any questions, please contact us.',
        footer_style,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_a4(order):
    """Build payment receipt PDF in A4 format; returns bytes."""
    from datetime import datetime
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor('#1e3a5f')
    slate = colors.HexColor('#334155')
    slate_light = colors.HexColor('#64748b')
    border_light = colors.HexColor('#e2e8f0')
    accent = colors.HexColor('#0f766e')

    title_style = ParagraphStyle(
        'ReceiptTitle', parent=styles['Heading1'],
        fontSize=22, spaceAfter=4, textColor=navy, fontName='Helvetica-Bold',
    )
    meta_style = ParagraphStyle(
        'Meta', parent=styles['Normal'], fontSize=9, textColor=slate_light, spaceAfter=0,
    )
    section_style = ParagraphStyle(
        'SectionHead', parent=styles['Normal'],
        fontSize=9, textColor=slate, spaceAfter=4, fontName='Helvetica-Bold',
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontSize=10, textColor=slate, spaceAfter=2,
    )
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=8, textColor=slate_light,
        alignment=1, spaceBefore=24, spaceAfter=0,
    )
    story = []

    logo_path = os.path.join(current_app.static_folder, 'logo.jpg')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = 1.75 * inch
                max_h_pt = 1.25 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                img = Image(logo_path, width=pw * scale, height=ph * scale)
            else:
                img = Image(logo_path, width=1.75 * inch, height=1.25 * inch)
            story.append(img)
            story.append(Spacer(1, 0.15 * inch))
        except Exception:
            pass

    story.append(Paragraph('PAYMENT RECEIPT', title_style))
    receipt_date = datetime.utcnow().strftime('%d %b %Y %H:%M')
    order_date = order.order_date.strftime('%d %b %Y') if order.order_date else '—'
    story.append(Paragraph(
        f'Order No. <b>{order.order_number}</b> &nbsp;·&nbsp; Order date {order_date} &nbsp;·&nbsp; Receipt date {receipt_date}',
        meta_style,
    ))
    story.append(Spacer(1, 0.35 * inch))

    story.append(Paragraph('PAYMENT DETAILS', section_style))
    pay_method = order.payment_method or '—'
    amount = float(order.grand_total or 0)
    story.append(Paragraph(f'<b>Amount paid:</b> {amount:.2f}', body_style))
    story.append(Paragraph(f'<b>Payment method:</b> {pay_method}', body_style))
    story.append(Paragraph(f'<b>Status:</b> {order.payment_status}', body_style))
    story.append(Spacer(1, 0.3 * inch))

    data = [['Product', 'Qty', 'Unit Price', 'Subtotal']]
    for oi in order.items:
        data.append([
            oi.product_name or '—',
            str(oi.quantity),
            '%.2f' % float(oi.selling_price),
            '%.2f' % float(oi.subtotal),
        ])
    col_widths = [3.2 * inch, 0.6 * inch, 1.1 * inch, 1.1 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), slate),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOX', (0, 0), (-1, -1), 0.5, border_light),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, border_light),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))
    total = float(order.total_amount or 0)
    discount = float(order.discount or 0)
    tax = float(order.tax or 0)
    totals_data = [['Subtotal', '%.2f' % total]]
    if discount != 0:
        totals_data.append(['Discount', '%.2f' % discount])
    if tax != 0:
        totals_data.append(['Tax', '%.2f' % tax])
    totals_data.append(['Amount paid', '%.2f' % amount])
    tot = Table(totals_data, colWidths=[1.5 * inch, 1.2 * inch])
    tot.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, accent),
    ]))
    story.append(tot)
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph('Thank you for your payment.', footer_style))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_thermal(order):
    """Build payment receipt PDF for thermal printer (80mm width); returns bytes."""
    from datetime import datetime
    # 80mm width in points (80 * 72 / 25.4 ≈ 227)
    thermal_width = 80 * mm
    thermal_height = 842  # A4 height in pt; content flows, printer uses actual content
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=(thermal_width, thermal_height),
        rightMargin=12, leftMargin=12, topMargin=14, bottomMargin=14,
    )
    styles = getSampleStyleSheet()
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=10, alignment=1, spaceAfter=2,
    )
    center_bold = ParagraphStyle(
        'CenterBold', parent=styles['Normal'], fontSize=11, alignment=1, fontName='Helvetica-Bold', spaceAfter=4,
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'], fontSize=8, alignment=1, spaceAfter=1,
    )
    line_style = ParagraphStyle(
        'Line', parent=styles['Normal'], fontSize=8, alignment=1, spaceAfter=2,
    )
    story = []

    logo_path = os.path.join(current_app.static_folder, 'logo.jpg')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = 0.9 * inch
                max_h_pt = 0.55 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                img = Image(logo_path, width=pw * scale, height=ph * scale)
            else:
                img = Image(logo_path, width=0.9 * inch, height=0.55 * inch)
            story.append(img)
            story.append(Spacer(1, 0.1 * inch))
        except Exception:
            pass

    story.append(Paragraph('PAYMENT RECEIPT', center_bold))
    story.append(Paragraph('—' * 24, line_style))
    story.append(Paragraph(f'Order: {order.order_number}', small_style))
    story.append(Paragraph(f'Date: {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}', small_style))
    story.append(Paragraph('—' * 24, line_style))
    story.append(Paragraph(order.customer_name or '—', center_style))
    if order.phone:
        story.append(Paragraph(order.phone, small_style))
    story.append(Paragraph('—' * 24, line_style))

    for oi in order.items:
        name = (oi.product_name or '—')[:28]
        story.append(Paragraph(f'{name}', small_style))
        story.append(Paragraph(
            f'{oi.quantity} x {float(oi.selling_price):.2f} = {float(oi.subtotal):.2f}',
            small_style,
        ))
    story.append(Paragraph('—' * 24, line_style))
    total = float(order.total_amount or 0)
    discount = float(order.discount or 0)
    tax = float(order.tax or 0)
    grand = float(order.grand_total or 0)
    story.append(Paragraph(f'Subtotal: {total:.2f}', small_style))
    if discount != 0:
        story.append(Paragraph(f'Discount: {discount:.2f}', small_style))
    if tax != 0:
        story.append(Paragraph(f'Tax: {tax:.2f}', small_style))
    story.append(Paragraph(f'<b>TOTAL PAID: {grand:.2f}</b>', center_style))
    story.append(Paragraph('—' * 24, line_style))
    story.append(Paragraph(f'Payment: {order.payment_method or "—"}', small_style))
    story.append(Paragraph('Thank you!', center_bold))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@orders_bp.route('/<order_id>/pdf')
@login_required
def pdf(order_id):
    order = Order.query.get_or_404(order_id)
    pdf_bytes = _build_order_invoice_pdf(order)
    safe_number = "".join(c for c in order.order_number if c.isalnum() or c in '-_')
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'Invoice_{safe_number}.pdf',
    )


@orders_bp.route('/<order_id>/receipt')
@login_required
def receipt(order_id):
    order = Order.query.get_or_404(order_id)
    if order.payment_status not in ('paid', 'partial'):
        flash('Payment receipt is only available for paid or partially paid orders.', 'warning')
        return redirect(url_for('orders.detail', order_id=order.id))
    fmt = request.args.get('format', 'a4').lower()
    if fmt == 'thermal':
        pdf_bytes = _build_receipt_pdf_thermal(order)
    else:
        pdf_bytes = _build_receipt_pdf_a4(order)
    safe_number = "".join(c for c in order.order_number if c.isalnum() or c in '-_')
    download_name = f'Receipt_{safe_number}_thermal.pdf' if fmt == 'thermal' else f'Receipt_{safe_number}.pdf'
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=download_name,
    )


@orders_bp.route('/<order_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(order_id):
    order = Order.query.get_or_404(order_id)
    if order.order_status == 'completed':
        flash('Cannot edit completed order.', 'warning')
        return redirect(url_for('orders.detail', order_id=order.id))
    form = OrderForm(obj=order)
    if form.validate_on_submit():
        order.customer_name = form.customer_name.data
        order.phone = form.phone.data
        order.email = form.email.data
        order.discount = form.discount.data
        order.tax = form.tax.data
        order.payment_method = form.payment_method.data
        order.payment_status = form.payment_status.data
        order.order_status = form.order_status.data
        order.notes = form.notes.data
        db.session.commit()
        flash('Order updated.', 'success')
        return redirect(url_for('orders.detail', order_id=order.id))
    # Pre-populate items for viewing (same format as frontend expects)
    order_items_initial = [{
        'product_name': oi.product_name,
        'quantity': oi.quantity,
        'selling_price': str(oi.selling_price),
        'item_type': 'existing_product' if oi.product_id else 'manual_entry',
        'product_id': str(oi.product_id) if oi.product_id else None,
    } for oi in order.items]
    return render_template('orders/form.html', form=form, order=order, order_items_initial=order_items_initial, title='Edit Order')
