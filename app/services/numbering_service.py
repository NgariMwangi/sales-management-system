"""Order, quotation, and delivery number generation."""
from datetime import datetime
from sqlalchemy import func

from app import db
from app.models import Order, Quotation, Delivery
from config import Config


class NumberingService:
    @staticmethod
    def _next_sequence(prefix, model_class, number_column, date_part):
        pattern = f"{prefix}-{date_part}-%"
        last = (
            db.session.query(model_class)
            .filter(getattr(model_class, number_column).like(pattern))
            .order_by(getattr(model_class, number_column).desc())
            .first()
        )
        if last:
            parts = getattr(last, number_column).split("-")
            seq = int(parts[-1]) + 1
        else:
            seq = 1
        return f"{prefix}-{date_part}-{seq:04d}"

    @staticmethod
    def next_order_number():
        date_part = datetime.utcnow().strftime("%Y%m")
        return NumberingService._next_sequence(
            Config.ORDER_NUMBER_PREFIX, Order, "order_number", date_part
        )

    @staticmethod
    def next_quotation_number():
        date_part = datetime.utcnow().strftime("%Y%m")
        return NumberingService._next_sequence(
            Config.QUOTATION_NUMBER_PREFIX, Quotation, "quotation_number", date_part
        )

    @staticmethod
    def next_delivery_number():
        date_part = datetime.utcnow().strftime("%Y%m")
        return NumberingService._next_sequence(
            Config.DELIVERY_NUMBER_PREFIX, Delivery, "delivery_number", date_part
        )
