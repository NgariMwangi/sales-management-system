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
from app.forms import OrderForm
from app.models import Order, Product, Setting
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
    styles = getSampleStyleSheet()
    black = colors.black
    grey = colors.HexColor('#555555')

    company_name = Setting.get('company_name', '') or 'Company Name'
    company_phone = Setting.get('company_phone', '') or ''
    company_address = Setting.get('company_address', '') or ''
    contact_parts = []
    if company_phone:
        contact_parts.append('Tel: {}'.format(company_phone))
    if company_address:
        contact_parts.append(company_address.strip().replace('\n', ', '))
    contact_line = ' | '.join(contact_parts) if contact_parts else ''

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=18, spaceAfter=2, textColor=black, fontName='Helvetica-Bold', leftIndent=0, firstLineIndent=0,
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'], fontSize=9, textColor=grey, spaceAfter=0, leftIndent=0, firstLineIndent=0,
        rightIndent=0, bulletIndent=0,
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontSize=10, textColor=black, spaceAfter=2, leftIndent=0, firstLineIndent=0,
    )
    terms_style = ParagraphStyle(
        'Terms', parent=styles['Normal'], fontSize=9, textColor=black, spaceAfter=2, leftIndent=0, firstLineIndent=0,
    )
    story = []

    # ----- Header: same as quotation (header image or logo + company) -----
    static_dir = current_app.static_folder
    header_path = None
    for name in ('header.jpg', 'header.png', 'header.jpeg'):
        p = os.path.join(static_dir, name)
        if os.path.isfile(p):
            header_path = p
            break
    if header_path:
        try:
            ir = ImageReader(header_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = 6.0 * inch
                max_h_pt = 1.4 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                header_img = Image(header_path, width=pw * scale, height=ph * scale)
            else:
                header_img = Image(header_path, width=6.0 * inch, height=1.4 * inch)
            header_img.hAlign = 'LEFT'
            story.append(header_img)
            story.append(Spacer(1, 0.2 * inch))
            story.append(_LineFlowable(frame_width))
        except Exception:
            header_path = None
    if not header_path:
        logo_path = os.path.join(static_dir, 'logo.jpg')
        logo_cell = Spacer(1, 1)
        if os.path.isfile(logo_path):
            try:
                ir = ImageReader(logo_path)
                pw, ph = ir.getSize()
                if pw and ph:
                    max_w_pt = 1.4 * inch
                    max_h_pt = 1.0 * inch
                    scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                    logo_cell = Image(logo_path, width=pw * scale, height=ph * scale)
                else:
                    logo_cell = Image(logo_path, width=1.4 * inch, height=1.0 * inch)
            except Exception:
                pass
        right_content = [
            Paragraph('<b>{}</b>'.format(company_name.replace('<', '&lt;')), ParagraphStyle('Company', parent=styles['Normal'], fontSize=14, textColor=black, spaceAfter=2, fontName='Helvetica-Bold')),
            Paragraph(contact_line or ' ', small_style),
        ]
        header_table = Table([[logo_cell, right_content]], colWidths=[1.5 * inch, 4.5 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('VALIGN', (1, 0), (1, 0), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('LEFTPADDING', (1, 0), (1, 0), 12),
        ]))
        story.append(header_table)
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
    col_widths = [frame_width - 2.9 * inch, 0.6 * inch, 1.1 * inch, 1.2 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, -1), 6),
        ('LEFTPADDING', (1, 0), (-1, -1), 6),
        ('RIGHTPADDING', (1, 0), (-1, -1), 0),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
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
    _desc_w = frame_width - 2.9 * inch
    _qty_w = 0.6 * inch
    _unit_w = 1.1 * inch
    _amt_w = 1.2 * inch

    # Subtotal row (aligned with Unit Price column)
    subtotal_row = Table([['', 'Subtotal', '%.2f' % total]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
    subtotal_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(subtotal_row)
    if discount != 0:
        disc_row = Table([['', 'Discount', '%.2f' % discount]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
        disc_row.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('LEFTPADDING', (1, 0), (1, 0), 0),
        ]))
        story.append(disc_row)
    if tax != 0:
        tax_row = Table([['', 'Tax', '%.2f' % tax]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
        tax_row.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('LEFTPADDING', (1, 0), (1, 0), 0),
        ]))
        story.append(tax_row)
    total_row = Table([['', 'Total Amount', '%.2f' % grand]], colWidths=[_desc_w, _qty_w + _unit_w, _amt_w])
    total_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
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
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
    ]))
    story.append(name_sig_table)
    story.append(Spacer(1, 0.15 * inch))
    date_data = [['Date:', '_________________________']]
    date_table = Table(date_data, colWidths=[0.5 * inch, frame_width - 0.5 * inch])
    date_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
    ]))
    story.append(date_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_a4(order):
    """Build payment receipt PDF in A4 format; same layout as thermal receipt, uses receipt logo.png."""
    from datetime import datetime
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
    )
    a4_width_pt = A4[0]
    content_width = a4_width_pt - 108  # 54*2 margins
    styles = getSampleStyleSheet()
    black = colors.black

    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=11, alignment=1, spaceAfter=4, textColor=black,
        leftIndent=0, firstLineIndent=0,
    )
    center_bold = ParagraphStyle(
        'CenterBold', parent=styles['Normal'], fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=4, textColor=black,
        leftIndent=0, firstLineIndent=0,
    )
    left_style = ParagraphStyle(
        'Left', parent=styles['Normal'], fontSize=10, alignment=0, spaceAfter=2, textColor=black,
        leftIndent=0, firstLineIndent=0,
    )
    left_bold = ParagraphStyle(
        'LeftBold', parent=styles['Normal'], fontSize=10, alignment=0, fontName='Helvetica-Bold', spaceAfter=2, textColor=black,
        leftIndent=0, firstLineIndent=0,
    )
    right_bold = ParagraphStyle(
        'RightBold', parent=styles['Normal'], fontSize=10, alignment=2, fontName='Helvetica-Bold', spaceAfter=2, textColor=black,
    )
    line_style = ParagraphStyle(
        'Line', parent=styles['Normal'], fontSize=10, alignment=1, spaceAfter=6,
    )
    story = []

    # Logo (receipt logo.png)
    logo_path = os.path.join(current_app.static_folder, 'receipt logo.png')
    if os.path.isfile(logo_path):
        try:
            ir = ImageReader(logo_path)
            pw, ph = ir.getSize()
            if pw and ph:
                max_w_pt = min(content_width, 3.5 * inch)
                max_h_pt = 1.2 * inch
                scale = min(max_w_pt / pw, max_h_pt / ph, 1.0)
                img = Image(logo_path, width=pw * scale, height=ph * scale)
            else:
                img = Image(logo_path, width=min(content_width, 3.5 * inch), height=1.2 * inch)
            story.append(img)
            story.append(Spacer(1, 0.15 * inch))
        except Exception:
            pass

    story.append(Paragraph('—' * 40, line_style))

    # Receipt No (left) and Date (right)
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
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 0.12 * inch))

    # Customer: table with zero left padding for alignment
    customer_cell = Paragraph('Customer: <b>{}</b>'.format((order.customer_name or '—').replace('<', '&lt;')), left_style)
    customer_table = Table([[customer_cell]], colWidths=[content_width])
    customer_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(customer_table)
    story.append(Paragraph('—' * 40, line_style))

    # Item table: Item/Description | Qty | Unit Price | Amount (no borders)
    col_w = [content_width * 0.45, content_width * 0.12, content_width * 0.2, content_width * 0.23]
    data = [['Item / Description', 'Qty', 'Unit Price', 'Amount']]
    for oi in order.items:
        data.append([
            (oi.product_name or '—')[:50],
            str(oi.quantity),
            '{:,.2f}'.format(float(oi.selling_price)),
            '{:,.2f}'.format(float(oi.subtotal)),
        ])
    grand = float(order.grand_total or 0)
    data.append([
        Paragraph('<b>TOTAL</b>', left_bold),
        '', '', Paragraph('<b>{:,.2f}</b>'.format(grand), right_bold),
    ])
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Paragraph('—' * 40, line_style))
    story.append(Paragraph('Payment: {}'.format(order.payment_method or '—'), center_style))

    story.append(Paragraph('Thank you for your business', center_bold))
    story.append(Paragraph('Goods once sold are not refundable', center_style))
    story.append(Paragraph('—' * 40, line_style))
    story.append(Paragraph('Authorised Signature / Stamp', center_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_receipt_pdf_thermal(order):
    """Build payment receipt PDF for thermal printer (80mm width); format matches receipt template."""
    from datetime import datetime
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
        'Center', parent=styles['Normal'], fontSize=9, alignment=1, spaceAfter=2,
    )
    center_bold = ParagraphStyle(
        'CenterBold', parent=styles['Normal'], fontSize=10, alignment=1, fontName='Helvetica-Bold', spaceAfter=2,
    )
    left_style = ParagraphStyle(
        'Left', parent=styles['Normal'], fontSize=8, alignment=0, spaceAfter=1,
        leftIndent=0, firstLineIndent=0,
    )
    left_bold = ParagraphStyle(
        'LeftBold', parent=styles['Normal'], fontSize=8, alignment=0, fontName='Helvetica-Bold', spaceAfter=1,
        leftIndent=0, firstLineIndent=0,
    )
    right_bold = ParagraphStyle(
        'RightBold', parent=styles['Normal'], fontSize=8, alignment=2, fontName='Helvetica-Bold', spaceAfter=1,
    )
    line_style = ParagraphStyle(
        'Line', parent=styles['Normal'], fontSize=8, alignment=1, spaceAfter=2,
    )
    story = []

    # Logo (receipt logo.png)
    logo_path = os.path.join(current_app.static_folder, 'receipt logo.png')
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
            story.append(Spacer(1, 0.08 * inch))
        except Exception:
            pass

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
        ('FONTSIZE', (0, 0), (-1, -1), 8),
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

    # Item table: Item/Description | Qty | Unit Price | Amount
    col_w = [content_width * 0.42, content_width * 0.14, content_width * 0.22, content_width * 0.22]
    data = [['Item / Description', 'Qty', 'Unit Price', 'Amount']]
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
        Paragraph('<b>TOTAL</b>', left_bold),
        '', '', Paragraph('<b>{:,.0f}</b>'.format(grand), right_bold),
    ])
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
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
