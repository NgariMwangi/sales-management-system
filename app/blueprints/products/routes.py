"""Product routes."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.blueprints.products import products_bp
from app.decorators import role_required
from app.forms import ProductForm, ProductStockForm
from app.models import Product, Category
from app.services import ProductService
from app.services.audit_service import AuditService


def _category_choices():
    return [('', '-- No category --')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]


@products_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    category_id = request.args.get('category', '').strip()
    stock_filter = request.args.get('stock', '')
    query = Product.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
            )
        )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if stock_filter == 'low':
        query = query.filter(Product.min_stock_level > 0, Product.stock_quantity <= Product.min_stock_level)
    elif stock_filter == 'out':
        query = query.filter(Product.stock_quantity <= 0)
    products = query.order_by(Product.name).paginate(page=page, per_page=20)
    categories = Category.query.order_by(Category.name).all()
    return render_template(
        'products/list.html',
        products=products,
        categories=categories,
        search=search,
        category_id=category_id,
        stock_filter=stock_filter,
    )


@products_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def add():
    form = ProductForm()
    form.category_id.choices = _category_choices()
    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            sku=form.sku.data or None,
            category_id=form.category_id.data or None,
            buying_price=form.buying_price.data if form.buying_price.data is not None else None,
            selling_price=form.selling_price.data if form.selling_price.data is not None else None,
            stock_quantity=form.stock_quantity.data if form.stock_quantity.data is not None else 0,
            min_stock_level=form.min_stock_level.data if form.min_stock_level.data is not None else 0,
            description=form.description.data or None,
        )
        db.session.add(product)
        db.session.commit()
        AuditService.log('product.create', 'Product', product.id, product.name, current_user.id)
        flash('Product added.', 'success')
        return redirect(url_for('products.list'))
    return render_template('products/form.html', form=form, title='Add Product')


@products_bp.route('/<product_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    form.category_id.choices = _category_choices()
    if form.validate_on_submit():
        product.name = form.name.data
        product.sku = form.sku.data or None
        product.category_id = form.category_id.data or None
        product.buying_price = form.buying_price.data if form.buying_price.data is not None else None
        product.selling_price = form.selling_price.data if form.selling_price.data is not None else None
        product.stock_quantity = form.stock_quantity.data if form.stock_quantity.data is not None else 0
        product.min_stock_level = form.min_stock_level.data if form.min_stock_level.data is not None else 0
        product.description = form.description.data or None
        db.session.commit()
        AuditService.log('product.update', 'Product', product.id, product.name, current_user.id)
        flash('Product updated.', 'success')
        return redirect(url_for('products.list'))
    form.category_id.data = product.category_id
    return render_template('products/form.html', form=form, product=product, title='Edit Product')


@products_bp.route('/<product_id>/stock', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'sales')
def stock(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductStockForm()
    if form.validate_on_submit():
        try:
            ProductService.adjust_stock(
                product_id,
                form.quantity.data,
                form.operation.data,
                form.reason.data,
            )
            flash('Stock updated.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
        return redirect(url_for('products.list'))
    return render_template('products/stock.html', form=form, product=product)


@products_bp.route('/<product_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def delete(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    AuditService.log('product.delete', 'Product', product.id, product.name, current_user.id)
    flash('Product deactivated.', 'success')
    return redirect(url_for('products.list'))


@products_bp.route('/api/search')
@login_required
def api_search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    products = Product.query.filter(
        Product.is_active == True,
        db.or_(
            Product.name.ilike(f'%{q}%'),
            Product.sku.ilike(f'%{q}%'),
        ),
    ).limit(15).all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'sku': p.sku or '',
            'selling_price': str(p.selling_price) if p.selling_price is not None else '0',
            'stock_quantity': p.stock_quantity,
        }
    for p in products])


@products_bp.route('/<product_id>/sales-history')
@login_required
def sales_history(product_id):
    from app.models import OrderItem, Order
    product = Product.query.get_or_404(product_id)
    items = (
        OrderItem.query.filter_by(product_id=product_id)
        .join(Order)
        .order_by(Order.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template('products/sales_history.html', product=product, items=items)
