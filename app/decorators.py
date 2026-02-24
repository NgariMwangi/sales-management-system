"""Role-based access control decorators."""
from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*roles):
    """Require user to have one of the given roles."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(f):
    return role_required('admin')(f)


def manager_required(f):
    return role_required('admin', 'manager')(f)


def sales_required(f):
    return role_required('admin', 'manager', 'sales')(f)


def delivery_required(f):
    return role_required('admin', 'manager', 'delivery')(f)


def users_manage_required(f):
    """Only admin can manage users."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_manage_users():
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def reports_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_view_reports():
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def settings_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_manage_settings():
            abort(403)
        return f(*args, **kwargs)
    return wrapped
