"""Order forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, DateField
from wtforms.validators import DataRequired, Optional, Email, NumberRange
from wtforms import FieldList, FormField


class OrderItemForm(FlaskForm):
    item_type = SelectField('Type', choices=[
        ('existing_product', 'From Catalog'),
        ('manual_entry', 'Manual Entry'),
    ], validators=[DataRequired()])
    product_id = StringField('Product ID', validators=[Optional()])
    product_name = StringField('Product Name', validators=[DataRequired()])
    quantity = StringField('Quantity', validators=[DataRequired()])
    selling_price = StringField('Price', validators=[DataRequired()])
    subtotal = StringField('Subtotal', validators=[Optional()])


class OrderForm(FlaskForm):
    customer_name = StringField('Customer Name', validators=[DataRequired()])
    phone = StringField('Phone', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    discount = DecimalField('Discount', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    tax = DecimalField('Tax %', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    payment_method = SelectField('Payment Method', choices=[
        ('', 'Select...'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank', 'Bank Transfer'),
        ('other', 'Other'),
    ], validators=[Optional()])
    payment_status = SelectField('Payment Status', choices=[
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('cancelled', 'Cancelled'),
    ], default='pending', validators=[DataRequired()])
    order_status = SelectField('Order Status', choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
