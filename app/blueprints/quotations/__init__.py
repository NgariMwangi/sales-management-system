"""Quotations blueprint."""
from flask import Blueprint

quotations_bp = Blueprint('quotations', __name__)

from app.blueprints.quotations import routes
