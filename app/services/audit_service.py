"""Audit logging service."""
from flask import request
from app import db
from app.models import AuditLog


class AuditService:
    @staticmethod
    def log(action, entity_type=None, entity_id=None, details=None, user_id=None):
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(entry)
        db.session.commit()
