"""Quotation forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, DateField
from wtforms.validators import DataRequired, Optional, Email, NumberRange


class QuotationItemForm(FlaskForm):
    item_type = SelectField('Type *', choices=[
        ('existing_product', 'From Catalog'),
        ('manual_entry', 'Manual Entry'),
    ], validators=[DataRequired()])
    product_id = StringField('Product ID', validators=[Optional()])
    product_name = StringField('Product Name *', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    quantity = StringField('Quantity *', validators=[DataRequired()])
    unit_price = StringField('Unit Price *', validators=[DataRequired()])
    discount_percent = StringField('Discount %', validators=[Optional()], default='0')
    subtotal = StringField('Subtotal', validators=[Optional()])


class QuotationForm(FlaskForm):
    customer_name = StringField('Customer Name *', validators=[DataRequired()])
    phone = StringField('Phone', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    valid_until = DateField('Valid Until', validators=[Optional()], format='%Y-%m-%d')
    discount = DecimalField('Discount', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    tax = DecimalField('Tax %', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    status = SelectField('Status *', choices=[
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='draft', validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
