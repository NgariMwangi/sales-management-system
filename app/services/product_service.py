"""Product business logic."""
from decimal import Decimal
from app import db
from app.models import Product


class ProductService:
    @staticmethod
    def adjust_stock(product_id, quantity, operation="add", reason=None):
        product = Product.query.get_or_404(product_id)
        q = int(quantity)
        if operation == "remove":
            if product.stock_quantity < q:
                raise ValueError("Insufficient stock")
            product.stock_quantity -= q
        else:
            product.stock_quantity += q
        db.session.commit()
        return product

    @staticmethod
    def get_low_stock_products():
        return Product.query.filter(
            Product.is_active == True,
            Product.min_stock_level > 0,
            Product.stock_quantity <= Product.min_stock_level,
        ).all()
