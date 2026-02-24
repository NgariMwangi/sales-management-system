"""Category form."""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length


class CategoryForm(FlaskForm):
    name = StringField('Category Name *', validators=[DataRequired(), Length(1, 100)])
    description = TextAreaField('Description', validators=[Optional(), Length(0, 500)])
