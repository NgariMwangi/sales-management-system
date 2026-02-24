"""User management routes (admin only)."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app import db
from app.blueprints.users import users_bp
from app.decorators import users_manage_required
from app.forms import UserForm
from app.models import User
from app.services import AuditService


@users_bp.route('/')
@login_required
@users_manage_required
def list():
    users = User.query.order_by(User.username).all()
    return render_template('users/list.html', users=users)


@users_bp.route('/add', methods=['GET', 'POST'])
@login_required
@users_manage_required
def add():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'danger')
            return render_template('users/form.html', form=form, title='Add User')
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already exists.', 'danger')
            return render_template('users/form.html', form=form, title='Add User')
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            role=form.role.data,
            is_active=form.is_active.data,
        )
        user.set_password(form.password.data or 'changeme')
        db.session.add(user)
        db.session.commit()
        AuditService.log('user.create', 'User', user.id, user.username)
        flash('User added.', 'success')
        return redirect(url_for('users.list'))
    return render_template('users/form.html', form=form, title='Add User')


@users_bp.route('/<user_id>/edit', methods=['GET', 'POST'])
@login_required
@users_manage_required
def edit(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        existing = User.query.filter(User.username == form.username.data, User.id != user.id).first()
        if existing:
            flash('Username already exists.', 'danger')
            return render_template('users/form.html', form=form, user=user, title='Edit User')
        existing = User.query.filter(User.email == form.email.data, User.id != user.id).first()
        if existing:
            flash('Email already exists.', 'danger')
            return render_template('users/form.html', form=form, user=user, title='Edit User')
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        AuditService.log('user.update', 'User', user.id, user.username)
        flash('User updated.', 'success')
        return redirect(url_for('users.list'))
    return render_template('users/form.html', form=form, user=user, title='Edit User')
