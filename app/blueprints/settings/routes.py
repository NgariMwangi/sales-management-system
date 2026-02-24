"""Settings routes (company info, tax, audit log)."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app import db
from app.blueprints.settings import settings_bp
from app.decorators import settings_required, admin_required
from app.models import Setting, AuditLog


@settings_bp.route('/')
@login_required
@settings_required
def index():
    company_name = Setting.get('company_name', '')
    company_address = Setting.get('company_address', '')
    tax_rate = Setting.get('tax_rate', '0')
    currency = Setting.get('currency', 'KSH')
    return render_template(
        'settings/index.html',
        company_name=company_name,
        company_address=company_address,
        tax_rate=tax_rate,
        currency=currency,
    )


@settings_bp.route('/save', methods=['POST'])
@login_required
@settings_required
def save():
    Setting.set('company_name', request.form.get('company_name'), 'company')
    Setting.set('company_address', request.form.get('company_address'), 'company')
    Setting.set('tax_rate', request.form.get('tax_rate'), 'general')
    Setting.set('currency', request.form.get('currency'), 'general')
    flash('Settings saved.', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('settings/audit_log.html', logs=logs)
