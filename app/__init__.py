"""Flask application factory."""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

from config import config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()


def create_app(config_name=None):
    """Create and configure the Flask application."""
    if config_name is None:
        config_name = __import__('os').environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config[config_name])
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    # Register blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.categories import categories_bp
    from app.blueprints.products import products_bp
    from app.blueprints.orders import orders_bp
    from app.blueprints.quotations import quotations_bp
    from app.blueprints.deliveries import deliveries_bp
    from app.blueprints.reports import reports_bp
    from app.blueprints.users import users_bp
    from app.blueprints.settings import settings_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(categories_bp, url_prefix='/categories')
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(orders_bp, url_prefix='/orders')
    app.register_blueprint(quotations_bp, url_prefix='/quotations')
    app.register_blueprint(deliveries_bp, url_prefix='/deliveries')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    
    # Error handlers
    from app.blueprints.errors import register_error_handlers
    register_error_handlers(app)
    
    # Context processors
    @app.context_processor
    def inject_globals():
        from flask import request
        return {
            'current_route': request.endpoint if request else None,
        }
    
    # Auto-create tables in development, testing, and production.
    # Ignore "already exists" so multiple workers or existing DB don't crash the app.
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate key" in str(e).lower():
                pass  # Tables/types already present (e.g. another worker or prior run)
            else:
                raise

    return app
