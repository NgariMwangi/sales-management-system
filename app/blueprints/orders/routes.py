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
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    BaseDocTemplate, PageTemplate, Frame, Flowable,
)

from app import db
from app.blueprints.orders import orders_bp
from app.decorators import role_required
from app.pdf_fonts import register_pdf_fonts, get_pdf_fonts
from app.forms import OrderForm
from app.models import Order, Product
from app.services import OrderService, AuditService


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


class _LineFlowable(Flowable):
    """Draws a horizontal line at full width; aligns with frame left edge."""
    def __init__(self, width_pt, height_pt=2):
        self.width_pt = width_pt
        self.height_pt = height_pt

    def wrap(self, aW, aH):
        return (self.width_pt, self.height_pt)

    def drawOn(self, canv, x, y, _sW=0):
        canv.setStrokeColor(colors.HexColor('#cccccc'))
        canv.setLineWidth(0.5)
        canv.line(x, y - self.height_pt, x + self.width_pt, y - self.height_pt)


def _hline(width_pt):
    """Thin horizontal line (grey), full frame width."""
    t = Table([['']], colWidths=[width_pt], rowHeights=[2])
    t.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_order_invoice_pdf(order):
    """Build invoice PDF in same format as quotation (header, layout, full-width tables); returns bytes."""
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
    terms_style = ParagraphStyle(
        'Terms', parent=styles['Normal'], fontSize=10, textColor=black, spaceAfter=2, leftIndent=0, firstLineIndent=0,
        fontName=fonts['regular'],
    )
    story = []

    # ----- Header: same as quotation (logo.png at half size + address) -----
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

    # ----- INVOICE title -----
    story.append(Paragraph('INVOICE', title_style))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.12 * inch))

    # ----- Invoice No (left) Date (right) -----
    order_date = order.order_date.strftime('%d/%m/%Y') if order.order_date else '—'
    ref_table = Table([
        [Paragraph('Invoice No: <b>{}</b>'.format(order.order_number), small_style),
         Paragraph('Date: <b>{}</b>'.format(order_date), ParagraphStyle('SmallRight', parent=small_style, alignment=2))]
    ], colWidths=[frame_width - 2.5 * inch, 2.5 * inch])
    ref_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 0.25 * inch))

    # ----- Customer -----
    story.append(Paragraph('Customer:', body_style))
    story.append(Paragraph(order.customer_name or '—', body_style))
    if order.phone:
        story.append(Paragraph('Tel: {}'.format(order.phone), small_style))
    if order.email:
        story.append(Paragraph('Email: {}'.format(order.email), small_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.2 * inch))

    # ----- Items table: Item/Description | Qty | Unit Price | Amount (full frame width, same as quotation) -----
    data = [['Item / Description', 'Qty', 'Unit Price', 'Amount']]
    for oi in order.items:
        data.append([
            oi.product_name or '—',
            str(oi.quantity),
            '%.2f' % float(oi.selling_price),
            '%.2f' % float(oi.subtotal),
        ])
    # Narrower Item/Description, width distributed to Qty, Unit Price, Amount
    col_widths = [frame_width - 4.1 * inch, 1.0 * inch, 1.5 * inch, 1.6 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, -1), 6),
        ('LEFTPADDING', (1, 0), (-1, -1), 6),
        ('RIGHTPADDING', (1, 0), (-1, -1), 0),
        ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.08 * inch))
    story.append(_hline(frame_width))

    total = float(order.total_amount or 0)
    discount = float(order.discount or 0)
    tax = float(order.tax or 0)
    grand = float(order.grand_total or 0)
    _desc_w = frame_width - 4.1 * inch
    _qty_w = 1.0 * inch
    _unit_w = 1.5 * inch
    _amt_w = 1.6 * inch

    # Subtotal row (aligned with Unit Price column)
    subtotal_row = Table([['', 'Subtotal', '%.2f' % total]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
    subtotal_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(subtotal_row)
    if discount != 0:
        disc_row = Table([['', 'Discount', '%.2f' % discount]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
        disc_row.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('LEFTPADDING', (1, 0), (1, 0), 0),
        ]))
        story.append(disc_row)
    if tax != 0:
        tax_row = Table([['', 'Tax', '%.2f' % tax]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
        tax_row.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('LEFTPADDING', (1, 0), (1, 0), 0),
        ]))
        story.append(tax_row)
    total_row = Table([['', 'Total Amount', '%.2f' % grand]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
    total_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(total_row)
    story.append(Spacer(1, 0.35 * inch))

    # ----- Payment terms / notes -----
    story.append(Paragraph('<b>Payment:</b>', terms_style))
    story.append(Paragraph('Payment is due as per agreed terms. Thank you for your business.', terms_style))
    if order.notes:
        story.append(Paragraph('<b>Notes:</b> ' + order.notes.replace('\n', ', '), terms_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.25 * inch))

    # ----- Authorised Signature -----
    story.append(Paragraph('Authorised by:', body_style))
    story.append(Spacer(1, 0.12 * inch))
    name_sig_data = [['Name:', '_________________________', 'Signature:', '_________________________']]
    name_sig_table = Table(
        name_sig_data,
        colWidths=[0.5 * inch, 2.2 * inch, 0.9 * inch, frame_width - 3.6 * inch],
    )
    name_sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
    ]))
    story.append(name_sig_table)
    story.append(Spacer(1, 0.15 * inch))
    date_data = [['Date:', '_________________________']]
    date_table = Table(date_data, colWidths=[0.5 * inch, frame_width - 0.5 * inch])
    date_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
    ]))
    story.append(date_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_a4(order):
    """Build payment receipt PDF in A4 format; same layout as invoice (header, table, styles) with receipt features."""
    from datetime import datetime
    register_pdf_fonts(current_app.static_folder)
    fonts = get_pdf_fonts()
    buffer = BytesIO()
    margin = 50
    pw_pt, ph_pt = A4[0], A4[1]
    frame_width = pw_pt - 2 * margin
    frame_height = ph_pt - 2 * margin
    frame = Frame(
        margin, margin, frame_width, frame_height,
        id='normal',
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc = BaseDocTemplate(
        buffer, pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
    )
    doc.addPageTemplates([PageTemplate(id='First', frames=[frame]), PageTemplate(id='Later', frames=[frame])])
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
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=11, alignment=1, spaceAfter=4, textColor=black,
        fontName=fonts['regular'],
    )
    center_bold = ParagraphStyle(
        'CenterBold', parent=styles['Normal'], fontSize=12, alignment=1, fontName=fonts['bold'], spaceAfter=4, textColor=black,
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

    # ----- RECEIPT title -----
    story.append(Paragraph('RECEIPT', title_style))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.12 * inch))

    # ----- Receipt No (left) Date (right) -----
    receipt_date = datetime.utcnow().strftime('%d/%m/%Y')
    ref_table = Table([
        [Paragraph('Receipt No: <b>{}</b>'.format(order.order_number), small_style),
         Paragraph('Date: <b>{}</b>'.format(receipt_date), ParagraphStyle('SmallRight', parent=small_style, alignment=2))]
    ], colWidths=[frame_width - 2.5 * inch, 2.5 * inch])
    ref_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 0.25 * inch))

    # ----- Customer (same as invoice) -----
    story.append(Paragraph('Customer:', body_style))
    story.append(Paragraph(order.customer_name or '—', body_style))
    if order.phone:
        story.append(Paragraph('Tel: {}'.format(order.phone), small_style))
    if order.email:
        story.append(Paragraph('Email: {}'.format(order.email), small_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.2 * inch))

    # ----- Items table: same columns as invoice -----
    data = [['Item / Description', 'Qty', 'Unit Price', 'Amount']]
    for oi in order.items:
        data.append([
            oi.product_name or '—',
            str(oi.quantity),
            '%.2f' % float(oi.selling_price),
            '%.2f' % float(oi.subtotal),
        ])
    _desc_w = frame_width - 4.1 * inch
    _qty_w = 1.0 * inch
    _unit_w = 1.5 * inch
    _amt_w = 1.6 * inch
    col_widths = [_desc_w, _qty_w, _unit_w, _amt_w]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, -1), 6),
        ('LEFTPADDING', (1, 0), (-1, -1), 6),
        ('RIGHTPADDING', (1, 0), (-1, -1), 0),
        ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.08 * inch))
    story.append(_hline(frame_width))

    # ----- Total row (same column alignment as invoice Subtotal/Total Amount) -----
    grand = float(order.grand_total or 0)
    total_row = Table([['', 'TOTAL', '%.2f' % grand]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
    total_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(total_row)
    story.append(Spacer(1, 0.25 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.15 * inch))

    # ----- Receipt features: Payment, thank you, disclaimer, signature -----
    story.append(Paragraph('Payment: {}'.format(order.payment_method or '—'), body_style))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph('Thank you for your business', center_bold))
    story.append(Paragraph('Goods once sold are not refundable', center_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph('Authorised Signature / Stamp', center_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_thermal(order):
    """Build payment receipt PDF for thermal printer (80mm width); format matches receipt template."""
    from datetime import datetime
    register_pdf_fonts(current_app.static_folder)
    fonts = get_pdf_fonts()
    thermal_width = 80 * mm
    thermal_height = 842
    content_width = thermal_width - 24
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=(thermal_width, thermal_height),
        rightMargin=12, leftMargin=12, topMargin=14, bottomMargin=14,
    )
    styles = getSampleStyleSheet()
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=10, alignment=1, spaceAfter=2, fontName=fonts['regular'],
    )
    center_bold = ParagraphStyle(
        'CenterBold', parent=styles['Normal'], fontSize=11, alignment=1, fontName=fonts['bold'], spaceAfter=2,
    )
    left_style = ParagraphStyle(
        'Left', parent=styles['Normal'], fontSize=9, alignment=0, spaceAfter=1,
        leftIndent=0, firstLineIndent=0, fontName=fonts['regular'],
    )
    left_bold = ParagraphStyle(
        'LeftBold', parent=styles['Normal'], fontSize=9, alignment=0, fontName=fonts['bold'], spaceAfter=1,
        leftIndent=0, firstLineIndent=0,
    )
    right_bold = ParagraphStyle(
        'RightBold', parent=styles['Normal'], fontSize=9, alignment=2, fontName=fonts['bold'], spaceAfter=1,
    )
    line_style = ParagraphStyle(
        'Line', parent=styles['Normal'], fontSize=9, alignment=1, spaceAfter=2, fontName=fonts['regular'],
    )
    story = []

    # Logo (logo.png – same as invoice) + address below
    logo_path = os.path.join(current_app.static_folder, 'logo.png')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = content_width
                max_h_pt = 0.5 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                img = Image(logo_path, width=pw * scale, height=ph * scale)
            else:
                img = Image(logo_path, width=content_width, height=0.5 * inch)
            story.append(img)
        except Exception:
            pass
    story.append(Spacer(1, 0.06 * inch))
    addr_style = ParagraphStyle(
        'AddrThermal', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#555555'),
        alignment=1, leftIndent=0, spaceAfter=0, spaceBefore=0, fontName=fonts['regular'],
    )
    story.append(Paragraph('Tel: 0725799182 | Gikomba, Kombo Munyiri Rd.', addr_style))
    story.append(Spacer(1, 0.06 * inch))

    story.append(Paragraph('—' * 20, line_style))

    # Receipt No (left) and Date (right) on one line
    receipt_date = datetime.utcnow().strftime('%d/%m/%Y')
    ref_table = Table([[
        Paragraph('Receipt No: <b>{}</b>'.format(order.order_number), left_style),
        Paragraph('Date: {}'.format(receipt_date), left_style),
    ]], colWidths=[content_width * 0.5, content_width * 0.5])
    ref_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 0.06 * inch))

    # Customer: use table with zero left padding so it aligns with Receipt No
    customer_cell = Paragraph('Customer: <b>{}</b>'.format((order.customer_name or '—').replace('<', '&lt;')), left_style)
    customer_table = Table([[customer_cell]], colWidths=[content_width])
    customer_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(customer_table)
    story.append(Paragraph('—' * 20, line_style))

    # Item table: Item | Qty | Unit Price | Amount
    # Narrower Item, width distributed to Qty, Unit Price, Amount
    col_w = [content_width * 0.26, content_width * 0.20, content_width * 0.27, content_width * 0.27]
    data = [['Item', 'Qty', 'Unit Price', 'Amount']]
    for oi in order.items:
        name = (oi.product_name or '—')[:24]
        data.append([
            name,
            str(oi.quantity),
            '{:,.0f}'.format(float(oi.selling_price)),
            '{:,.0f}'.format(float(oi.subtotal)),
        ])
    grand = float(order.grand_total or 0)
    data.append([
        '', Paragraph('<b>TOTAL</b>', left_bold), '', Paragraph('<b>{:,.0f}</b>'.format(grand), right_bold),
    ])
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Paragraph('—' * 20, line_style))
    story.append(Paragraph('Payment: {}'.format(order.payment_method or '—'), center_style))

    # Thank you and disclaimer
    story.append(Paragraph('Thank you for your business', center_bold))
    story.append(Paragraph('Goods once sold are not refundable', center_style))
    story.append(Paragraph('—' * 20, line_style))
    story.append(Paragraph('Authorised Signature / Stamp', center_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@orders_bp.route('/<order_id>/pdf')
@login_required
def pdf(order_id):
    order = Order.query.get_or_404(order_id)
    pdf_bytes = _build_order_invoice_pdf(order)
    safe_number = "".join(c for c in order.order_number if c.isalnum() or c in '-_')
    view_inline = request.args.get('view') == '1'
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=not view_inline,
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
    view_inline = request.args.get('view') == '1'
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=not view_inline,
        download_name=download_name,
    )


@orders_bp.route('/<order_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(order_id):
    order = Order.query.get_or_404(order_id)
    # Only admin and manager may edit completed orders; sales cannot
    role = (current_user.role or '').strip().lower()
    if (order.order_status or '').strip().lower() == 'completed' and role not in ('admin', 'manager'):
        flash('Cannot edit completed order. Only admin or manager can edit completed orders.', 'warning')
        return redirect(url_for('orders.detail', order_id=order.id))
    form = OrderForm(obj=order)
    if form.validate_on_submit():
        was_completed = order.order_status == 'completed'
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
        details = 'Order {} updated'.format(order.order_number)
        if was_completed:
            details += ' (completed order edited by {})'.format(current_user.role)
        AuditService.log('order.update', 'Order', order.id, details, current_user.id)
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
