"""Delivery forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateField
from wtforms.validators import DataRequired, Optional


class DeliveryItemForm(FlaskForm):
    product_name = StringField('Product Name *', validators=[DataRequired()])
    quantity = StringField('Quantity *', validators=[DataRequired()])
    unit_price = StringField('Unit Price', validators=[Optional()], default='0')


class DeliveryForm(FlaskForm):
    delivery_type = SelectField('Delivery Type *', choices=[
        ('order', 'From Order'),
        ('standalone', 'Standalone'),
    ], validators=[DataRequired()])
    order_id = StringField('Order', validators=[Optional()])
    customer_name = StringField('Customer Name *', validators=[DataRequired()])
    phone = StringField('Phone', validators=[Optional()])
    delivery_address = TextAreaField('Delivery Address *', validators=[DataRequired()])
    scheduled_date = DateField('Scheduled Date', validators=[Optional()], format='%Y-%m-%d')
    status = SelectField('Status *', choices=[
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', validators=[DataRequired()])
    assigned_to_id = SelectField('Assigned To', validators=[Optional()], choices=[])
    delivery_notes = TextAreaField('Delivery Notes', validators=[Optional()])
    items_description = TextAreaField('Items Description (standalone)', validators=[Optional()])
