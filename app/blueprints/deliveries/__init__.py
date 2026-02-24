"""Deliveries blueprint."""
from flask import Blueprint

deliveries_bp = Blueprint('deliveries', __name__)

from app.blueprints.deliveries import routes
