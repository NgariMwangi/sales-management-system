"""Categories blueprint."""
from flask import Blueprint

categories_bp = Blueprint('categories', __name__)

from app.blueprints.categories import routes
