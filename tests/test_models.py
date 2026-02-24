"""Basic model and auth tests."""
import pytest
from app import create_app, db
from app.models import User, Product, Order


@pytest.fixture
def app():
    app = create_app('testing')
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield


@pytest.fixture
def db_ctx(app, app_ctx):
    db.create_all()
    yield
    db.session.remove()
    db.drop_all()


def test_user_password_hash(db_ctx):
    u = User(username='test', email='test@test.com', role='sales')
    u.set_password('secret')
    assert u.check_password('secret')
    assert not u.check_password('wrong')


def test_user_roles(db_ctx):
    admin = User(username='a', email='a@a.com', role='admin')
    assert admin.is_admin()
    assert admin.can_manage_users()
    sales = User(username='s', email='s@s.com', role='sales')
    assert not sales.can_manage_users()
    assert sales.can_manage_orders()


def test_product_low_stock(db_ctx):
    p = Product(name='Widget', stock_quantity=5, min_stock_level=10, selling_price=10)
    db.session.add(p)
    db.session.commit()
    assert p.is_low_stock
    assert not p.is_out_of_stock
    p.stock_quantity = 0
    assert p.is_out_of_stock
