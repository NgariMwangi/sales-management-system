"""Flask-WTF forms."""
from app.forms.auth import LoginForm, RegisterForm, ChangePasswordForm
from app.forms.user import UserForm
from app.forms.category import CategoryForm
from app.forms.product import ProductForm, ProductStockForm
from app.forms.order import OrderForm, OrderItemForm
from app.forms.quotation import QuotationForm, QuotationItemForm
from app.forms.delivery import DeliveryForm, DeliveryItemForm
from app.forms.report import ReportFilterForm

__all__ = [
    'LoginForm',
    'RegisterForm',
    'ChangePasswordForm',
    'UserForm',
    'CategoryForm',
    'ProductForm',
    'ProductStockForm',
    'OrderForm',
    'OrderItemForm',
    'QuotationForm',
    'QuotationItemForm',
    'DeliveryForm',
    'DeliveryItemForm',
    'ReportFilterForm',
]
