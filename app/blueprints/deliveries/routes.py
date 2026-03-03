"""Delivery routes."""
import os
import json
from io import BytesIO

from flask import render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageTemplate, Frame, Flowable,
)

from app import db
from app.blueprints.deliveries import deliveries_bp
from app.decorators import role_required
from app.pdf_fonts import register_pdf_fonts, get_pdf_fonts
from app.forms import DeliveryForm
from app.models import Delivery, DeliveryItem, Order, User
from app.services import DeliveryService


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


@deliveries_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    query = Delivery.query
    if current_user.role == 'delivery':
        query = query.filter(Delivery.assigned_to_id == current_user.id)
    if status:
        query = query.filter(Delivery.status == status)
    deliveries = query.order_by(Delivery.scheduled_date.desc().nullslast(), Delivery.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('deliveries/list.html', deliveries=deliveries, status=status)


@deliveries_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales', 'delivery')
def add():
    form = DeliveryForm()
    form.assigned_to_id.choices = [('', '-- Select --')] + [
        (u.id, u.full_name or u.username) for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
    ]
    orders = Order.query.filter(Order.order_status != 'cancelled').order_by(Order.created_at.desc()).limit(100).all()
    if form.validate_on_submit():
        delivery_type = form.delivery_type.data
        if delivery_type == 'order':
            order_id = form.order_id.data
            if not order_id:
                flash('Select an order.', 'danger')
                return render_template('deliveries/form.html', form=form, orders=orders, title='New Delivery')
            items_json = request.form.get('item_quantities_json', '{}')
            try:
                item_quantities = json.loads(items_json) if items_json else {}
            except Exception:
                item_quantities = {}
            delivery = DeliveryService.create_from_order(
                order_id=order_id,
                customer_name=form.customer_name.data,
                phone=form.phone.data,
                delivery_address=form.delivery_address.data,
                scheduled_date=form.scheduled_date.data,
                assigned_to_id=form.assigned_to_id.data or None,
                notes=form.delivery_notes.data,
                item_quantities=item_quantities,
            )
        else:
            items_json = request.form.get('items_json', '[]')
            try:
                items_data = json.loads(items_json) if items_json else []
            except Exception:
                items_data = []
            if not items_data:
                flash('Add at least one item for standalone delivery.', 'danger')
                return render_template('deliveries/form.html', form=form, orders=orders, title='New Delivery')
            delivery = DeliveryService.create_standalone(
                customer_name=form.customer_name.data,
                phone=form.phone.data,
                delivery_address=form.delivery_address.data,
                items_data=items_data,
                scheduled_date=form.scheduled_date.data,
                assigned_to_id=form.assigned_to_id.data or None,
                notes=form.delivery_notes.data,
            )
        flash('Delivery created.', 'success')
        return redirect(url_for('deliveries.detail', delivery_id=delivery.id))
    return render_template('deliveries/form.html', form=form, orders=orders, title='New Delivery')


@deliveries_bp.route('/<delivery_id>')
@login_required
def detail(delivery_id):
    delivery = Delivery.query.get_or_404(delivery_id)
    if current_user.role == 'delivery' and delivery.assigned_to_id != current_user.id:
        from flask import abort
        abort(403)
    return render_template('deliveries/detail.html', delivery=delivery)


@deliveries_bp.route('/<delivery_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(delivery_id):
    delivery = Delivery.query.get_or_404(delivery_id)
    if current_user.role == 'delivery' and delivery.assigned_to_id != current_user.id:
        from flask import abort
        abort(403)
    form = DeliveryForm(obj=delivery)
    form.assigned_to_id.choices = [('', '-- Select --')] + [
        (u.id, u.full_name or u.username) for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
    ]
    if form.validate_on_submit():
        delivery.customer_name = form.customer_name.data
        delivery.phone = form.phone.data
        delivery.delivery_address = form.delivery_address.data
        delivery.scheduled_date = form.scheduled_date.data
        delivery.assigned_to_id = form.assigned_to_id.data or None
        delivery.status = form.status.data
        delivery.delivery_notes = form.delivery_notes.data
        items_json = request.form.get('items_json', '[]')
        try:
            items_data = json.loads(items_json) if items_json else []
        except Exception:
            items_data = []
        for di in delivery.items.all():
            db.session.delete(di)
        for row in items_data:
            product_name = (row.get('product_name') or '').strip() or '—'
            quantity = int(row.get('quantity', 0) or 0)
            unit_price = float(row.get('unit_price', 0) or 0)
            if product_name and quantity > 0:
                db.session.add(DeliveryItem(
                    delivery_id=delivery.id,
                    product_name=product_name,
                    quantity=quantity,
                    unit_price=unit_price,
                ))
        db.session.commit()
        flash('Delivery updated.', 'success')
        return redirect(url_for('deliveries.detail', delivery_id=delivery.id))
    items_initial = [{'product_name': di.product_name, 'quantity': di.quantity, 'unit_price': float(di.unit_price)} for di in delivery.items]
    return render_template('deliveries/edit.html', form=form, delivery=delivery, items_initial=items_initial)


def _build_delivery_report_pdf(delivery):
    """Build delivery note PDF with same header as quotation; layout matches delivery note template."""
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
    border_light = colors.HexColor('#e2e8f0')

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=20, spaceAfter=2, textColor=black, fontName=fonts['bold'],
        leftIndent=0, firstLineIndent=0,
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'], fontSize=10, textColor=grey, spaceAfter=0,
        leftIndent=0, firstLineIndent=0, rightIndent=0, bulletIndent=0, fontName=fonts['regular'],
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontSize=11, textColor=black, spaceAfter=2,
        leftIndent=0, firstLineIndent=0, fontName=fonts['regular'],
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

    # ----- DELIVERY NOTE (left) -----
    story.append(Paragraph('DELIVERY NOTE', title_style))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.12 * inch))

    # ----- Delivery Note No (left) Date (right) -----
    date_str = delivery.scheduled_date.strftime('%d/%m/%Y') if delivery.scheduled_date else (delivery.created_at.strftime('%d/%m/%Y') if delivery.created_at else '—')
    ref_table = Table([
        [Paragraph('Delivery Note No: <b>{}</b>'.format(delivery.delivery_number), small_style),
         Paragraph('Date: <b>{}</b>'.format(date_str), ParagraphStyle('SmallRight', parent=small_style, alignment=2))]
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
    story.append(Paragraph(delivery.customer_name or '—', body_style))
    if delivery.phone:
        story.append(Paragraph('Tel: {}'.format(delivery.phone), small_style))
    story.append(Spacer(1, 0.15 * inch))

    # ----- Delivery Address -----
    story.append(Paragraph('Delivery Address:', body_style))
    story.append(Paragraph((delivery.delivery_address or '—').replace('\n', '<br/>'), body_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(_hline(frame_width))
    story.append(Spacer(1, 0.2 * inch))

    # ----- Items table: Item/Description | Qty Delivered | Remarks -----
    data = [['Item / Description', 'Qty Delivered', 'Remarks']]
    for di in delivery.items:
        data.append([di.product_name or '—', str(di.quantity), ''])
    # Narrower Item/Description, wider Remarks; part of description width given to Qty Delivered
    col_widths = [frame_width - 3.8 * inch, 1.3 * inch, 2.5 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), fonts['bold']),
        ('FONTNAME', (0, 1), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (0, -1), 8),
        ('LEFTPADDING', (1, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.5, border_light),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, border_light),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.25 * inch))

    # ----- Received by: Name/Signature row, then Date/Date row (left and right) -----
    story.append(Paragraph('Received by:', body_style))
    story.append(Spacer(1, 0.12 * inch))
    _nc = [0.5 * inch, 2.2 * inch, 0.9 * inch, frame_width - 3.6 * inch]
    received_table = Table([
        ['Name:', '_________________________', 'Signature:', '_________________________'],
        ['Date:', '_________________________', '', ''],
    ], colWidths=_nc)
    received_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), fonts['regular']),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
    ]))
    story.append(received_table)
    story.append(Spacer(1, 0.25 * inch))

    # ----- Goods received disclaimer (centered) -----
    disclaimer_style = ParagraphStyle(
        'Disclaimer', parent=styles['Normal'], fontSize=11, textColor=black, alignment=1, spaceAfter=0, fontName=fonts['regular'],
    )
    story.append(Paragraph('Goods received in good condition', disclaimer_style))
    story.append(Spacer(1, 0.3 * inch))

    # ----- Footer: Tel centered -----
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=10, textColor=grey, alignment=1, spaceAfter=0, fontName=fonts['regular'],
    )
    story.append(Paragraph('Tel: 0725 799182', footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@deliveries_bp.route('/<delivery_id>/pdf')
@login_required
def pdf(delivery_id):
    delivery = Delivery.query.get_or_404(delivery_id)
    if current_user.role == 'delivery' and delivery.assigned_to_id != current_user.id:
        from flask import abort
        abort(403)
    pdf_bytes = _build_delivery_report_pdf(delivery)
    safe_number = "".join(c for c in delivery.delivery_number if c.isalnum() or c in '-_')
    view_inline = request.args.get('view') == '1'
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=not view_inline,
        download_name=f'Delivery_Report_{safe_number}.pdf',
    )


@deliveries_bp.route('/<delivery_id>/update-status', methods=['POST'])
@login_required
def update_status(delivery_id):
    delivery = Delivery.query.get_or_404(delivery_id)
    if current_user.role == 'delivery' and delivery.assigned_to_id != current_user.id:
        from flask import abort
        abort(403)
    new_status = request.form.get('status')
    if new_status in Delivery.STATUSES:
        delivery.status = new_status
        if new_status == 'delivered':
            from datetime import datetime
            delivery.delivery_date = datetime.utcnow()
        if delivery.order_id:
            delivery.order.delivery_status = new_status
        db.session.commit()
        flash('Status updated.', 'success')
    return redirect(url_for('deliveries.detail', delivery_id=delivery.id))
