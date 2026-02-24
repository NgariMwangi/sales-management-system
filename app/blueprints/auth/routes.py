"""Auth routes."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.blueprints.auth import auth_bp
from app.forms import LoginForm, RegisterForm, ChangePasswordForm
from app.models import User


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Create first user only. Disable/remove this after bootstrapping."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if User.query.count() > 0:
        flash('Registration is closed. An admin account already exists.', 'info')
        return redirect(url_for('auth.login'))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data or None,
            role='admin',
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Account created. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('auth.login'))
        if not user.is_active:
            flash('Account is disabled.', 'danger')
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next') or url_for('dashboard.index')
        return redirect(next_page)
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('auth.profile'))
        if form.new_password.data != form.confirm_password.data:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('auth.profile'))
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash('Password updated.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html', form=form)
