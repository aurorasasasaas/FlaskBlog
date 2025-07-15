from datetime import datetime, timezone, timedelta, date
from hashlib import md5
import json
import secrets
from time import time
from typing import Optional
import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import current_app, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import rq
from app import db, login
from app.search import add_to_index, remove_from_index, query_index



class SearchableMixin:
    @classmethod
    def search(cls, expression, page, per_page):
        try:
            ids, total = query_index(cls.__tablename__, expression, page, per_page)
        except Exception as e:
            # Fallback to basic DB filtering by matching the expression in a text field
            query = db.session.query(cls).filter(cls.body.ilike(f'%{expression}%'))  # for Post or adjust for your model
            total = query.count()
            results = query.offset((page-1)*per_page).limit(per_page).all()
            return results, total

        if total == 0:
            return [], 0
        when = [(id_, i) for i, id_ in enumerate(ids)]
        query = sa.select(cls).where(cls.id.in_(ids)).order_by(
            db.case(*when, value=cls.id)
        )
        return db.session.scalars(query), total


    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted),
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                try:
                    if current_app.elasticsearch:
                        add_to_index(obj.__tablename__, obj)
                except Exception as e:
                    print(f"Elasticsearch add_to_index error (add): {e}")
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                try:
                    if current_app.elasticsearch:
                        add_to_index(obj.__tablename__, obj)
                except Exception as e:
                    print(f"Elasticsearch add_to_index error (update): {e}")
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                try:
                    if current_app.elasticsearch:
                        remove_from_index(obj.__tablename__, obj)
                except Exception as e:
                    print(f"Elasticsearch remove_from_index error (delete): {e}")
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in db.session.scalars(sa.select(cls)):
            add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)


class PaginatedAPIMixin:
    @staticmethod
    def to_collection_dict(query, page, per_page, endpoint, **kwargs):
        resources = db.paginate(query, page=page, per_page=per_page, error_out=False)
        return {
            'items': [item.to_dict() for item in resources.items],
            '_meta': {
                'page': page,
                'per_page': per_page,
                'total_pages': resources.pages,
                'total_items': resources.total,
            },
            '_links': {
                'self': url_for(endpoint, page=page, per_page=per_page, **kwargs),
                'next': url_for(endpoint, page=page + 1, per_page=per_page, **kwargs) if resources.has_next else None,
                'prev': url_for(endpoint, page=page - 1, per_page=per_page, **kwargs) if resources.has_prev else None,
            },
        }


followers = sa.Table(
    'followers',
    db.metadata,
    sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'), primary_key=True),
    sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'), primary_key=True)
)


class User(PaginatedAPIMixin, UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
    last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    last_message_read_time: so.Mapped[Optional[datetime]]
    token: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32), index=True, unique=True)
    token_expiration: so.Mapped[Optional[datetime]]
    study_goal: so.Mapped[Optional[str]] = so.mapped_column(sa.Text)
    birth_date: so.Mapped[Optional[date]] = so.mapped_column(sa.Date, nullable=True)
    profile_pic: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128), nullable=True)
    status = db.Column(db.String(20))
    school = db.Column(db.String(140))
    social_link = db.Column(db.String(140))
    is_admin = db.Column(db.Boolean, default=False)  # Admin flag

    posts: so.DynamicMapped['Post'] = so.relationship('Post', back_populates='author', lazy='dynamic')

    following: so.DynamicMapped['User'] = so.relationship(
        'User',
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        back_populates='followers',
        lazy='dynamic',
    )

    followers: so.DynamicMapped['User'] = so.relationship(
        'User',
        secondary=followers,
        primaryjoin=(followers.c.followed_id == id),
        secondaryjoin=(followers.c.follower_id == id),
        back_populates='following',
        lazy='dynamic',
    )

    messages_sent: so.DynamicMapped['Message'] = so.relationship(
        'Message', foreign_keys='Message.sender_id', back_populates='author', lazy='dynamic'
    )
    messages_received: so.DynamicMapped['Message'] = so.relationship(
        'Message', foreign_keys='Message.recipient_id', back_populates='recipient', lazy='dynamic'
    )

    notifications: so.DynamicMapped['Notification'] = so.relationship('Notification', back_populates='user', lazy='dynamic')
    tasks: so.DynamicMapped['Task'] = so.relationship('Task', back_populates='user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        if self.profile_pic:
            return url_for('static', filename='profile_pics/' + self.profile_pic)
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'

    def follow(self, user):
        if not self.is_following(user):
            self.following.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.following.remove(user)

    def is_following(self, user):
        return self.following.filter(followers.c.followed_id == user.id).count() > 0

    def followers_count(self):
        return self.followers.count()

    def following_count(self):
        return self.following.count()

    def posts_count(self):
        return self.posts.count()

    def following_posts(self):
        return (
            Post.query.join(followers, (followers.c.followed_id == Post.user_id))
            .filter(followers.c.follower_id == self.id)
            .order_by(Post.timestamp.desc())
        )

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256'
        )

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
        except Exception:
            return None
        return db.session.get(User, id)

    def unread_message_count(self):
        last_read = self.last_message_read_time or datetime(1900, 1, 1)
        return (
            self.messages_received
            .filter(Message.timestamp > last_read)
            .count()
        )

    def add_notification(self, name, data):
        self.notifications.filter_by(name=name).delete()
        n = Notification(name=name, payload_json=json.dumps(data), user=self)
        db.session.add(n)
        return n

    def launch_task(self, name, description, *args, **kwargs):
        rq_job = current_app.task_queue.enqueue(f'app.tasks.{name}', self.id, *args, **kwargs)
        task = Task(id=rq_job.get_id(), name=name, description=description, user=self)
        db.session.add(task)
        return task

    def get_tasks_in_progress(self):
        return self.tasks.filter_by(complete=False).all()

    def get_task_in_progress(self, name):
        return self.tasks.filter_by(name=name, complete=False).first()

    def to_dict(self, include_email=False):
        data = {
            'id': self.id,
            'username': self.username,
            'last_seen': self.last_seen.replace(tzinfo=timezone.utc).isoformat(),
            'about_me': self.about_me,
            'post_count': self.posts_count(),
            'follower_count': self.followers_count(),
            'following_count': self.following_count(),
            '_links': {
                'self': url_for('api.get_user', id=self.id),
                'followers': url_for('api.get_followers', id=self.id),
                'following': url_for('api.get_following', id=self.id),
                'avatar': self.avatar(128),
            },
        }
        if include_email:
            data['email'] = self.email
        return data

    def from_dict(self, data, new_user=False):
        for field in ['username', 'email', 'about_me']:
            if field in data:
                setattr(self, field, data[field])
        if new_user and 'password' in data:
            self.set_password(data['password'])

    def get_token(self, expires_in=3600):
        now = datetime.now(timezone.utc)
        if self.token and self.token_expiration and self.token_expiration.replace(tzinfo=timezone.utc) > now + timedelta(seconds=60):
            return self.token
        self.token = secrets.token_hex(16)
        self.token_expiration = now + timedelta(seconds=expires_in)
        db.session.add(self)
        return self.token

    def revoke_token(self):
        self.token_expiration = datetime.now(timezone.utc) - timedelta(seconds=1)

    @staticmethod
    def check_token(token):
        user = db.session.scalar(sa.select(User).where(User.token == token))
        if user is None or user.token_expiration is None or user.token_expiration.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None
        return user


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class Post(SearchableMixin, db.Model):
    __searchable__ = ['body']

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    body: so.Mapped[str] = so.mapped_column(sa.String(300))
    timestamp: so.Mapped[datetime] = so.mapped_column(index=True, default=lambda: datetime.now(timezone.utc))
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    language: so.Mapped[Optional[str]] = so.mapped_column(sa.String(5))
    category: so.Mapped[Optional[str]] = so.mapped_column(sa.String(50))
    custom_category: so.Mapped[Optional[str]] = so.mapped_column(sa.String(50))
    comments: so.Mapped[list['Comment']] = so.relationship(
    'Comment',
    back_populates='post',
    cascade='all, delete-orphan'
)
    author: so.Mapped[User] = so.relationship('User', back_populates='posts')

    def __repr__(self):
        return f'<Post {self.body[:20]}>'


class Message(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    sender_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    recipient_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    body: so.Mapped[str] = so.mapped_column(sa.String(140))
    timestamp: so.Mapped[datetime] = so.mapped_column(index=True, default=lambda: datetime.now(timezone.utc))

    author: so.Mapped[User] = so.relationship('User', foreign_keys=[sender_id], back_populates='messages_sent')
    recipient: so.Mapped[User] = so.relationship('User', foreign_keys=[recipient_id], back_populates='messages_received')

    def __repr__(self):
        return f'<Message {self.body[:20]}>'


class Notification(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    timestamp: so.Mapped[float] = so.mapped_column(index=True, default=time)
    payload_json: so.Mapped[str] = so.mapped_column(sa.Text)

    user: so.Mapped[User] = so.relationship('User', back_populates='notifications')

    def get_data(self):
        return json.loads(self.payload_json)


class Task(db.Model):
    id: so.Mapped[str] = so.mapped_column(sa.String(36), primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id))
    complete: so.Mapped[bool] = so.mapped_column(default=False)

    user: so.Mapped[User] = so.relationship('User', back_populates='tasks')

    def get_rq_job(self):
        pass

    def get_progress(self):
        pass


class Comment(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    body: so.Mapped[str] = so.mapped_column(sa.Text, nullable=False)
    timestamp: so.Mapped[datetime] = so.mapped_column(index=True, default=lambda: datetime.now(timezone.utc))
    author_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), nullable=False)
    post_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('post.id'), nullable=False)
    parent_id: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey('comment.id'), nullable=True)

    replies: so.DynamicMapped['Comment'] = so.relationship(
        'Comment',
        backref=so.backref('parent', remote_side=[id]),
        lazy='dynamic'
    )

    author: so.Mapped[User] = so.relationship('User', backref='comments')
    post: so.Mapped['Post'] = so.relationship('Post', back_populates='comments')

