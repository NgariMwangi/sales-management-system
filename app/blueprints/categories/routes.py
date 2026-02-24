"""Category routes."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app import db
from app.blueprints.categories import categories_bp
from app.decorators import role_required
from app.forms import CategoryForm
from app.models import Category
from app.services.audit_service import AuditService


@categories_bp.route('/')
@login_required
def list():
    categories = Category.query.order_by(Category.name).all()
    return render_template('categories/list.html', categories=categories)


@categories_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def add():
    form = CategoryForm()
    if form.validate_on_submit():
        existing = Category.query.filter_by(name=form.name.data.strip()).first()
        if existing:
            flash('A category with this name already exists.', 'danger')
            return render_template('categories/form.html', form=form, title='Add Category')
        category = Category(name=form.name.data.strip(), description=form.description.data or None)
        db.session.add(category)
        db.session.commit()
        AuditService.log('category.create', 'Category', category.id, category.name)
        flash('Category added.', 'success')
        return redirect(url_for('categories.list'))
    return render_template('categories/form.html', form=form, title='Add Category')


@categories_bp.route('/<category_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        other = Category.query.filter(Category.name == form.name.data.strip(), Category.id != category.id).first()
        if other:
            flash('A category with this name already exists.', 'danger')
            return render_template('categories/form.html', form=form, category=category, title='Edit Category')
        category.name = form.name.data.strip()
        category.description = form.description.data or None
        db.session.commit()
        AuditService.log('category.update', 'Category', category.id, category.name)
        flash('Category updated.', 'success')
        return redirect(url_for('categories.list'))
    return render_template('categories/form.html', form=form, category=category, title='Edit Category')


@categories_bp.route('/<category_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def delete(category_id):
    category = Category.query.get_or_404(category_id)
    product_count = category.products.count()
    if product_count > 0:
        flash(f'Cannot delete: {product_count} product(s) use this category. Remove the category from them first.', 'danger')
        return redirect(url_for('categories.list'))
    db.session.delete(category)
    db.session.commit()
    AuditService.log('category.delete', 'Category', category.id, category.name)
    flash('Category deleted.', 'success')
    return redirect(url_for('categories.list'))
