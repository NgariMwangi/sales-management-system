"""Quotation routes."""
import os
from io import BytesIO

from flask import render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import json

from app import db
from app.blueprints.quotations import quotations_bp
from app.decorators import role_required
from app.forms import QuotationForm
from app.models import Quotation
from app.services import QuotationService


@quotations_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    query = Quotation.query
    if status:
        query = query.filter(Quotation.status == status)
    quotations = query.order_by(Quotation.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('quotations/list.html', quotations=quotations, status=status)


@quotations_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def add():
    form = QuotationForm()
    if form.validate_on_submit():
        items_json = request.form.get('items_json', '[]')
        try:
            items_data = json.loads(items_json) if items_json else []
        except Exception:
            items_data = []
        if not items_data:
            flash('Add at least one item.', 'danger')
            return render_template('quotations/form.html', form=form, title='New Quotation')
        try:
            discount_val = form.discount.data
            tax_val = form.tax.data
            if discount_val is None:
                discount_val = 0
            if tax_val is None:
                tax_val = 0
            quo = QuotationService.create_quotation(
                customer_name=form.customer_name.data,
                phone=form.phone.data,
                email=form.email.data,
                valid_until=form.valid_until.data,
                items_data=items_data,
                discount=float(discount_val),
                tax=float(tax_val),
                status=form.status.data,
                notes=form.notes.data,
                created_by_id=current_user.id,
            )
            flash('Quotation created.', 'success')
            return redirect(url_for('quotations.detail', quotation_id=quo.id))
        except Exception as e:
            flash('Could not create quotation: {}'.format(str(e)), 'danger')
    elif request.method == 'POST' and form.errors:
        for field, errors in form.errors.items():
            for err in errors:
                flash(err if field == 'csrf_token' else '{}'.format(err), 'danger')
    return render_template('quotations/form.html', form=form, title='New Quotation')


@quotations_bp.route('/<quotation_id>')
@login_required
def detail(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    return render_template('quotations/detail.html', quotation=quotation)


def _build_quotation_pdf(quotation):
    """Build a professional quotation PDF; returns bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    # Professional color palette
    navy = colors.HexColor('#1e3a5f')
    slate = colors.HexColor('#334155')
    slate_light = colors.HexColor('#64748b')
    border_light = colors.HexColor('#e2e8f0')
    bg_row = colors.HexColor('#f8fafc')
    accent = colors.HexColor('#0f766e')  # teal accent for grand total

    title_style = ParagraphStyle(
        'QuotationTitle', parent=styles['Heading1'],
        fontSize=22, spaceAfter=4, textColor=navy, fontName='Helvetica-Bold',
    )
    meta_style = ParagraphStyle(
        'QuotationMeta', parent=styles['Normal'],
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

    # ----- Header: logo + title block -----
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

    story.append(Paragraph('QUOTATION', title_style))
    created = quotation.created_at.strftime('%d %b %Y') if quotation.created_at else '—'
    valid = quotation.valid_until.strftime('%d %b %Y') if quotation.valid_until else '—'
    story.append(Paragraph(
        f'Quotation No. <b>{quotation.quotation_number}</b> &nbsp;·&nbsp; '
        f'Date {created} &nbsp;·&nbsp; Valid until {valid}',
        meta_style,
    ))
    story.append(Spacer(1, 0.35 * inch))

    # ----- Bill To (customer card) -----
    story.append(Paragraph('BILL TO', section_style))
    story.append(Paragraph(quotation.customer_name or '—', body_style))
    if quotation.phone or quotation.email:
        parts = []
        if quotation.phone:
            parts.append(quotation.phone)
        if quotation.email:
            parts.append(quotation.email)
        story.append(Paragraph(' · '.join(parts), meta_style))
    story.append(Spacer(1, 0.4 * inch))

    # ----- Items table -----
    data = [['Product / Description', 'Qty', 'Unit Price', 'Disc %', 'Subtotal']]
    for qi in quotation.items:
        data.append([
            qi.product_name or '—',
            str(qi.quantity),
            '%.2f' % float(qi.unit_price),
            '%.2f' % float(qi.discount_percent or 0),
            '%.2f' % float(qi.subtotal),
        ])
    col_widths = [3.5 * inch, 0.6 * inch, 1.15 * inch, 0.7 * inch, 1.15 * inch]
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

    # ----- Totals (right-aligned block) -----
    total = float(quotation.total_amount or 0)
    discount = float(quotation.discount or 0)
    tax = float(quotation.tax or 0)
    grand = float(quotation.grand_total or 0)
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

    if quotation.notes:
        story.append(Spacer(1, 0.35 * inch))
        story.append(Paragraph('NOTES', section_style))
        notes_para = Paragraph(quotation.notes.replace('\n', '<br/>'), body_style)
        story.append(notes_para)

    # ----- Footer -----
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        'Thank you for your business. If you have any questions, please contact us.',
        footer_style,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@quotations_bp.route('/<quotation_id>/pdf')
@login_required
def pdf(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    pdf_bytes = _build_quotation_pdf(quotation)
    safe_number = "".join(c for c in quotation.quotation_number if c.isalnum() or c in '-_')
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'Quotation_{safe_number}.pdf',
    )


@quotations_bp.route('/<quotation_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    form = QuotationForm(obj=quotation)
    if form.validate_on_submit():
        items_json = request.form.get('items_json', '[]')
        try:
            items_data = json.loads(items_json) if items_json else []
        except Exception:
            items_data = []
        if not items_data:
            flash('Add at least one item.', 'danger')
        else:
            quotation.customer_name = form.customer_name.data
            quotation.phone = form.phone.data
            quotation.email = form.email.data
            quotation.valid_until = form.valid_until.data
            quotation.status = form.status.data
            quotation.notes = form.notes.data
            discount_val = form.discount.data if form.discount.data is not None else 0
            tax_val = form.tax.data if form.tax.data is not None else 0
            QuotationService.update_quotation_items(
                quotation, items_data, discount=float(discount_val), tax_percent=float(tax_val)
            )
            db.session.commit()
            flash('Quotation updated.', 'success')
            return redirect(url_for('quotations.detail', quotation_id=quotation.id))
    quotation_items_initial = [{
        'product_name': qi.product_name,
        'quantity': qi.quantity,
        'unit_price': str(qi.unit_price),
        'discount_percent': str(qi.discount_percent or 0),
        'item_type': 'existing_product' if qi.product_id else 'manual_entry',
        'product_id': str(qi.product_id) if qi.product_id else None,
    } for qi in quotation.items]
    return render_template('quotations/form.html', form=form, quotation=quotation, quotation_items_initial=quotation_items_initial, title='Edit Quotation')


@quotations_bp.route('/<quotation_id>/convert-to-order', methods=['POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def convert_to_order(quotation_id):
    order = QuotationService.convert_to_order(quotation_id, created_by_id=current_user.id)
    flash('Order created from quotation.', 'success')
    return redirect(url_for('orders.detail', order_id=order.id))
