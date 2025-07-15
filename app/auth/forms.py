from flask_wtf import FlaskForm
from flask_babel import _, lazy_gettext as _l
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo
import sqlalchemy as sa
import re
from app import db
from app.models import User


class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Sign In'))


from flask_wtf.file import FileField, FileAllowed
from wtforms.fields import DateField


class RegistrationForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    birth_date = DateField(_l('Birth Date'), format='%Y-%m-%d', validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(
        _l('Repeat Password'),
        validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Register'))

    def validate_password(self, password):
        p = password.data
        if len(p) < 8:
            raise ValidationError(_('Password must be at least 8 characters long.'))
        if not re.search(r'[A-Z]', p):
            raise ValidationError(_('Password must contain at least one uppercase letter.'))

    def validate_username(self, username):
        user = db.session.scalar(sa.select(User).where(User.username == username.data))
        if user is not None:
            raise ValidationError(_('Please use a different username.'))

    def validate_email(self, email):
        user = db.session.scalar(sa.select(User).where(User.email == email.data))
        if user is not None:
            raise ValidationError(_('Please use a different email address.'))

class ResetPasswordRequestForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Request Password Reset'))


class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(
        _l('Repeat Password'),
        validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Reset Password'))

    def validate_password(self, password):
        p = password.data
        if len(p) < 8:
            raise ValidationError(_('Password must be at least 8 characters long.'))
        if not re.search(r'[A-Z]', p):
            raise ValidationError(_('Password must contain at least one uppercase letter.'))

from flask_wtf.file import FileField, FileAllowed

