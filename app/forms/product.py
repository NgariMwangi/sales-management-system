"""Product forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, IntegerField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Optional, NumberRange


class ProductForm(FlaskForm):
    name = StringField('Product Name', validators=[DataRequired()])
    sku = StringField('SKU', validators=[Optional()])
    category_id = SelectField('Category', validators=[Optional()], choices=[], coerce=lambda x: x if x else None)
    buying_price = DecimalField('Buying Price', places=2, validators=[Optional(), NumberRange(min=0)])
    selling_price = DecimalField('Selling Price', places=2, validators=[Optional(), NumberRange(min=0)])
    stock_quantity = IntegerField('Stock Quantity', validators=[Optional(), NumberRange(min=0)])
    min_stock_level = IntegerField('Min Stock Level', validators=[Optional(), NumberRange(min=0)])
    description = TextAreaField('Description', validators=[Optional()])


class ProductStockForm(FlaskForm):
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    operation = SelectField('Operation', choices=[('add', 'Add'), ('remove', 'Remove')], validators=[DataRequired()])
    reason = StringField('Reason', validators=[Optional()])
