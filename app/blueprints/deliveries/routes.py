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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from app import db
from app.blueprints.deliveries import deliveries_bp
from app.decorators import role_required
from app.forms import DeliveryForm
from app.models import Delivery, Order, User
from app.services import DeliveryService


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


def _build_delivery_report_pdf(delivery):
    """Build a professional delivery report PDF; returns bytes."""
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
        'Title', parent=styles['Heading1'],
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

    story.append(Paragraph('DELIVERY REPORT', title_style))
    scheduled = delivery.scheduled_date.strftime('%d %b %Y') if delivery.scheduled_date else '—'
    delivered = delivery.delivery_date.strftime('%d %b %Y %H:%M') if delivery.delivery_date else '—'
    story.append(Paragraph(
        f'Delivery No. <b>{delivery.delivery_number}</b> &nbsp;·&nbsp; '
        f'Scheduled: {scheduled} &nbsp;·&nbsp; Status: {delivery.status}',
        meta_style,
    ))
    if delivery.order_id:
        story.append(Paragraph(f'Order: {delivery.order.order_number}', meta_style))
    story.append(Spacer(1, 0.35 * inch))

    story.append(Paragraph('DELIVERY TO', section_style))
    story.append(Paragraph(delivery.customer_name or '—', body_style))
    if delivery.phone:
        story.append(Paragraph(f'Phone: {delivery.phone}', meta_style))
    story.append(Paragraph('<b>Address:</b><br/>' + (delivery.delivery_address or '—').replace('\n', '<br/>'), body_style))
    assigned = '—'
    if getattr(delivery, 'assigned_to_user', None) and delivery.assigned_to_user:
        u = delivery.assigned_to_user
        assigned = u.full_name or u.username or '—'
    story.append(Paragraph(f'<b>Assigned to:</b> {assigned}', meta_style))
    story.append(Spacer(1, 0.35 * inch))

    data = [['Product / Description', 'Qty', 'Unit Price']]
    for di in delivery.items:
        data.append([
            di.product_name or '—',
            str(di.quantity),
            '%.2f' % float(di.unit_price),
        ])
    col_widths = [4.2 * inch, 0.8 * inch, 1.4 * inch]
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

    if delivery.delivery_notes:
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph('NOTES', section_style))
        story.append(Paragraph(delivery.delivery_notes.replace('\n', '<br/>'), body_style))

    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph('RECEIVED BY (Customer signature)', section_style))
    story.append(Spacer(1, 0.15 * inch))
    sig_line = Table([['']], colWidths=[3.5 * inch], rowHeights=[0.45 * inch])
    sig_line.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, slate),
        ('BOX', (0, 0), (-1, -1), 0, colors.white),
    ]))
    story.append(sig_line)
    story.append(Spacer(1, 0.2 * inch))
    name_date_data = [
        ['Name:', ''],
        ['Date:', ''],
    ]
    name_date_table = Table(name_date_data, colWidths=[0.6 * inch, 2.9 * inch], rowHeights=[0.28 * inch, 0.28 * inch])
    name_date_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (0, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), slate),
        ('LINEBELOW', (1, 0), (1, 0), 0.5, slate),
        ('LINEBELOW', (1, 1), (1, 1), 0.5, slate),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(name_date_table)

    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph('Delivery report generated for records.', footer_style))
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
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
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
