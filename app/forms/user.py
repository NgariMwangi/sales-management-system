"""User forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional, EqualTo


class UserForm(FlaskForm):
    username = StringField('Username *', validators=[DataRequired(), Length(1, 80)])
    email = StringField('Email *', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Optional(), Length(0, 120)])
    role = SelectField('Role *', choices=[
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('sales', 'Sales'),
        ('delivery', 'Delivery'),
    ], validators=[DataRequired()])
    password = PasswordField('Password', validators=[Optional(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[Optional(), EqualTo('password')])
    is_active = BooleanField('Active', default=True)
