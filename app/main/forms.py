from flask import request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SubmitField, SelectField, TextAreaField,
    FileField, PasswordField, HiddenField
)
from wtforms.validators import (
    ValidationError, DataRequired, Length, Email, EqualTo, Optional
)
from flask_wtf.file import FileAllowed
import sqlalchemy as sa
from flask_babel import _, lazy_gettext as _l
from app import db
from app.models import User


class DeleteForm(FlaskForm):
    pass


class EditProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    about_me = TextAreaField(_l('About me'), validators=[Length(min=0, max=140)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = db.session.scalar(
                sa.select(User).where(User.username == username.data)
            )
            if user is not None:
                raise ValidationError(_('Please use a different username.'))


class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')


class PostForm(FlaskForm):
    post = TextAreaField(
        _l('Share your thoughts'),
        render_kw={
            "placeholder": "Write a little study note or reflection...",
            "class": "form-control form-control-lg mb-3",
            "rows": 4,
        },
        validators=[
            DataRequired(message="This field can’t be empty, bestie!"),
            Length(min=1, max=300)
        ]
    )
    category = SelectField(
        _l('Category'),
        choices=[
            ('notes', 'Notes'),
            ('revision', 'Revision'),
            ('motivation', 'Motivation'),
            ('quotes', 'Quotes'),
            ('study_tips', 'Study Tips'),
            ('resources', 'Resources'),
            ('goals', 'Goals'),
            ('questions', 'Questions'),
            ('daily_log', 'Daily Log'),
            ('planning', 'Planning'),
            ('other', 'Other')
        ],
        validators=[DataRequired()],
        render_kw={"class": "form-select mb-3"}
    )
    custom_category = StringField(
        _l('Custom Category'),
        render_kw={
            "placeholder": "Write your category...",
            "class": "form-control mb-3",
            "style": "display: none;"
        },
        validators=[Optional(), Length(max=50)]
    )
    submit = SubmitField(
        _l('Add to Study Log'),
        render_kw={"class": "btn btn-primary btn-block mt-2"}
    )

class SearchForm(FlaskForm):
    q = StringField(_l('Search'), validators=[DataRequired()])
    category = SelectField(
        _l('Category'),
        choices=[
            ('', 'All'),
            ('notes', 'Notes'),
            ('revision', 'Revision'),
            ('motivation', 'Motivation'),
            ('quotes', 'Quotes'),
            ('study_tips', 'Study Tips'),
            ('resources', 'Resources'),
            ('goals', 'Goals'),
            ('questions', 'Questions'),
            ('daily_log', 'Daily Log'),
            ('planning', 'Planning'),
            ('other', 'Other')
        ],
        validators=[Optional()],
        render_kw={"class": "form-select"}
    )

    def __init__(self, *args, **kwargs):
        if 'formdata' not in kwargs:
            kwargs['formdata'] = request.args
        if 'meta' not in kwargs:
            kwargs['meta'] = {'csrf': False}
        super(SearchForm, self).__init__(*args, **kwargs)


class MessageForm(FlaskForm):
    message = TextAreaField(
        _l('Message'),
        validators=[DataRequired(), Length(min=1, max=140)]
    )
    submit = SubmitField(_l('Submit'))


class UpdateAccountForm(FlaskForm):
    username = StringField(
        'Username',
        validators=[DataRequired(), Length(min=2, max=20)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email()]
    )
    picture = FileField(
        'Update Profile Picture',
        validators=[FileAllowed(['jpg', 'png'])]
    )
    submit = SubmitField('Update')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That email is taken. Please choose a different one.')


class RequestResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('There is no account with that email. You must register first.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password')]
    )
    submit = SubmitField('Reset Password')


class PasswordForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired()])
    new_password2 = PasswordField(
        'Repeat New Password',
        validators=[DataRequired(), EqualTo('new_password')]
    )
    submit = SubmitField('Change Password')

#comms
class CommentForm(FlaskForm):
    body = TextAreaField('Comment', validators=[DataRequired(), Length(min=1, max=500)])
    parent_id = HiddenField()  # To track if it’s a reply to another comment
    submit = SubmitField('Post')
      

class EditProfileForm(FlaskForm):
    status = SelectField('Status', choices=[
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('individual', 'Individual')
    ], validators=[Optional()])
    school = StringField('School or Organization', validators=[Optional(), Length(max=140)])
    about_me = TextAreaField('About me', validators=[Length(min=0, max=140)])
    social_link = StringField('Social Media Link', validators=[Optional()])
    submit = SubmitField('Save Changes')

