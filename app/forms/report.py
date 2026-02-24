"""Report filter form."""
from flask_wtf import FlaskForm
from wtforms import SelectField, DateField
from wtforms.validators import Optional, DataRequired


class ReportFilterForm(FlaskForm):
    report_type = SelectField('Report Type *', choices=[
        ('sales', 'Sales Report'),
        ('product_performance', 'Product Performance'),
        ('delivery_performance', 'Delivery Performance'),
        ('stock', 'Stock Report'),
    ], validators=[DataRequired()])
    date_from = DateField('From Date', validators=[Optional()], format='%Y-%m-%d')
    date_to = DateField('To Date', validators=[Optional()], format='%Y-%m-%d')
    format = SelectField('Export Format', choices=[
        ('html', 'View'),
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
    ], default='html', validators=[Optional()])
