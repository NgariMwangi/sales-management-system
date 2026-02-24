"""Authentication forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo


class LoginForm(FlaskForm):
    username = StringField('Username *', validators=[DataRequired(), Length(1, 80)])
    password = PasswordField('Password *', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me', default=False)


class RegisterForm(FlaskForm):
    """Temporary first-user registration (remove later)."""
    username = StringField('Username *', validators=[DataRequired(), Length(1, 80)])
    email = StringField('Email *', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Length(0, 120)])
    password = PasswordField('Password *', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password *', validators=[DataRequired(), EqualTo('password')])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password *', validators=[DataRequired()])
    new_password = PasswordField('New Password *', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password *', validators=[DataRequired()])
