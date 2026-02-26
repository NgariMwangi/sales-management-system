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
from reportlab.platypus import BaseDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageTemplate, Frame, Flowable
import json

from app import db
from app.blueprints.quotations import quotations_bp
from app.decorators import role_required
from app.forms import QuotationForm
from app.models import Quotation, Setting
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


class _LineFlowable(Flowable):
    """Draws a horizontal line at full width; no table so it aligns with frame left edge."""
    def __init__(self, width_pt, height_pt=2):
        self.width_pt = width_pt
        self.height_pt = height_pt

    def wrap(self, aW, aH):
        return (self.width_pt, self.height_pt)

    def drawOn(self, canv, x, y, _sW=0):
        canv.setStrokeColor(colors.HexColor('#cccccc'))
        canv.setLineWidth(0.5)
        # draw at bottom of flowable box so it sits under the content above
        canv.line(x, y - self.height_pt, x + self.width_pt, y - self.height_pt)


def _hline(width_pt=512):
    """Thin horizontal line (grey). Use _LineFlowable for header block so it aligns; Table elsewhere."""
    t = Table([['']], colWidths=[width_pt], rowHeights=[2])
    t.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_quotation_pdf(quotation):
    """Build quotation PDF in clean document format (logo, company header, customer, table, terms, acceptance)."""
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
    grey_light = colors.HexColor('#888888')

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

    # ----- Header: use header image (logo + name + contact) if present, else logo + company text -----
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
            # Same treatment as header: image then spacer then line as separate flowables (line uses custom draw so it starts at frame left)
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

    # ----- QUOTATION title -----
    story.append(Paragraph('QUOTATION', title_style))
    story.append(_hline())
    story.append(Spacer(1, 0.12 * inch))

    # ----- Quotation No (left) Date (right) -----
    created = quotation.created_at.strftime('%d/%m/%Y') if quotation.created_at else '—'
    # Full frame width (like header _hline) so table starts at document left margin
    ref_table = Table([
        [Paragraph('Quotation No: <b>{}</b>'.format(quotation.quotation_number), small_style),
         Paragraph('Date: <b>{}</b>'.format(created), ParagraphStyle('SmallRight', parent=small_style, alignment=2))]
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
    story.append(Paragraph(quotation.customer_name or '—', body_style))
    if quotation.phone:
        story.append(Paragraph('Tel: {}'.format(quotation.phone), small_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(_hline())
    story.append(Spacer(1, 0.2 * inch))

    # ----- Items table: Item/Description | Qty | Unit Price | Amount (full frame width like header) -----
    data = [['Item / Description', 'Qty', 'Unit Price', 'Amount']]
    for qi in quotation.items:
        data.append([
            qi.product_name or '—',
            str(qi.quantity),
            '%.2f' % float(qi.unit_price),
            '%.2f' % float(qi.subtotal),
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
    story.append(_hline())

    total = float(quotation.total_amount or 0)
    grand = float(quotation.grand_total or 0)
    # Subtotal starts where Unit Price starts; Total Quoted Amount starts where Qty starts
    _desc_w = frame_width - 2.9 * inch  # same as items table col0
    _qty_w = 0.6 * inch
    _unit_w = 1.1 * inch
    _amt_w = 1.2 * inch
    subtotal_row = Table([['', 'Subtotal', '%.2f' % total]], colWidths=[_desc_w + _qty_w, _unit_w, _amt_w])
    subtotal_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(subtotal_row)
    total_row = Table([['', 'Total Quoted Amount', '%.2f' % grand]], colWidths=[_desc_w, _qty_w + _unit_w, _amt_w])
    total_row.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(total_row)
    story.append(Spacer(1, 0.35 * inch))

    # ----- Terms & Conditions -----
    story.append(Paragraph('<b>Terms &amp; Conditions:</b>', terms_style))
    terms_list = [
        'Prices are valid for 7 days from the date above.',
        'Subject to availability and usual terms of trade.',
        'Delivery charges may apply.',
        'Payment is required upon delivery.',
    ]
    for term in terms_list:
        story.append(Paragraph('• ' + term, terms_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(_hline())
    story.append(Spacer(1, 0.25 * inch))

    # ----- Accepted by: Name, Signature, Date -----
    story.append(Paragraph('Accepted by:', body_style))
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
