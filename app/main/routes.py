from datetime import datetime, timezone
from flask import render_template, flash, redirect, url_for, request, g, current_app, abort
from flask_login import current_user, login_required
import sqlalchemy as sa
from langdetect import detect, LangDetectException
from app import db
from app.main.forms import EditProfileForm, EmptyForm, PostForm, SearchForm, MessageForm, CommentForm
from app.models import User, Post, Message, Notification, Comment
from app.main import bp
import random

@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()
        g.search_form = SearchForm()

@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    post_form = PostForm()
    delete_form = EmptyForm()
    comment_form = CommentForm()

    if post_form.validate_on_submit():
        try:
            language = detect(post_form.post.data)
        except LangDetectException:
            language = ''
        category = post_form.category.data
        custom_category = post_form.custom_category.data.strip() if post_form.custom_category.data else None

        post = Post(
            body=post_form.post.data,
            author=current_user,
            language=language,
            category=category,
            custom_category=custom_category if category == 'other' and custom_category else None
        )
        db.session.add(post)
        db.session.commit()
        flash('Your post is now live!')
        return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    query = current_user.following_posts().order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)

    return render_template(
        'index.html',
        title='Home',
        form=post_form,
        posts=posts.items,
        next_url=url_for('main.index', page=posts.next_num) if posts.has_next else None,
        prev_url=url_for('main.index', page=posts.prev_num) if posts.has_prev else None,
        delete_form=delete_form,
        comment_form=comment_form
    )

@bp.route('/explore')
@login_required
def explore():
    delete_form = EmptyForm()
    post_form = PostForm()
    comment_form = CommentForm()

    page = request.args.get('page', 1, type=int)
    query = sa.select(Post).order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)

    return render_template(
        'index.html',
        title='Explore',
        posts=posts.items,
        delete_form=delete_form,
        comment_form=comment_form,
        next_url=url_for('main.explore', page=posts.next_num) if posts.has_next else None,
        prev_url=url_for('main.explore', page=posts.prev_num) if posts.has_prev else None
    )

@bp.route('/user/<username>')
@login_required
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    delete_form = EmptyForm()
    post_form = PostForm()
    comment_form = CommentForm()

    page = request.args.get('page', 1, type=int)
    query = user.posts.order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)

    return render_template(
        'user.html',
        user=user,
        posts=posts.items,
        form=post_form,
        delete_form=delete_form,
        comment_form=comment_form,
        next_url=url_for('main.user', username=username, page=posts.next_num) if posts.has_next else None,
        prev_url=url_for('main.user', username=username, page=posts.prev_num) if posts.has_prev else None
    )

@bp.route('/user/<username>/popup')
def user_popup(username):
    user = User.query.filter_by(username=username).first_or_404()
    form = EmptyForm()
    return render_template('user_popup.html', user=user, form=form)

@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.status = form.status.data
        current_user.school = form.school.data
        current_user.about_me = form.about_me.data
        current_user.social_link = form.social_link.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('main.user', username=current_user.username))
    elif request.method == 'GET':
        form.status.data = current_user.status
        form.school.data = current_user.school
        form.about_me.data = current_user.about_me
        form.social_link.data = current_user.social_link

    QUOTES = [
        "Stay hungry. Stay foolish.",
        "Believe you can and you're halfway there.",
        "Be yourself; everyone else is already taken.",
        "Dream big and dare to fail.",
    ]

    return render_template(
        'edit_profile.html',
        title='Edit Profile',
        form=form,
        random_quote=random.choice(QUOTES)
    )

@bp.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f'User {username} not found.')
            return redirect(url_for('main.index'))
        if user == current_user:
            flash('You cannot follow yourself!')
            return redirect(url_for('main.user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(f'You are following {username}!')
        return redirect(url_for('main.user', username=username))
    return redirect(url_for('main.index'))

@bp.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f'User {username} not found.')
            return redirect(url_for('main.index'))
        if user == current_user:
            flash('You cannot unfollow yourself!')
            return redirect(url_for('main.user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(f'You are not following {username}.')
        return redirect(url_for('main.user', username=username))
    return redirect(url_for('main.index'))

@bp.route('/send_message/<recipient>', methods=['GET', 'POST'])
@login_required
def send_message(recipient):
    user = db.first_or_404(sa.select(User).where(User.username == recipient))
    form = MessageForm()
    if form.validate_on_submit():
        msg = Message(author=current_user, recipient=user, body=form.message.data)
        db.session.add(msg)
        user.add_notification('unread_message_count', user.unread_message_count())
        db.session.commit()
        flash('Your message has been sent.')
        return redirect(url_for('main.user', username=recipient))
    return render_template('send_message.html', title='Send Message', form=form, recipient=recipient)




@bp.route('/messages')
@login_required
def messages():
    current_user.last_message_read_time = datetime.now(timezone.utc)
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    
    page = request.args.get('page', 1, type=int)
    query = current_user.messages_received.order_by(Message.timestamp.desc())
    messages = db.paginate(query, page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)

    next_url = url_for('main.messages', page=messages.next_num) if messages.has_next else None
    prev_url = url_for('main.messages', page=messages.prev_num) if messages.has_prev else None

    comment_form = CommentForm()  # create the comment form

    return render_template(
        'messages.html',
        messages=messages.items,
        next_url=next_url,
        prev_url=prev_url,
        comment_form=comment_form  # pass it to the template
    )

@bp.route('/export_posts')
@login_required
def export_posts():
    if current_user.get_task_in_progress('export_posts'):
        flash('An export task is currently in progress')
    else:
        current_user.launch_task('export_posts', 'Exporting posts...')
        db.session.commit()
    return redirect(url_for('main.user', username=current_user.username))

@bp.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    query = current_user.notifications.filter(Notification.timestamp > since).order_by(Notification.timestamp.asc())
    notifications = query.all()
    return [{'name': n.name, 'data': n.get_data(), 'timestamp': n.timestamp} for n in notifications]

@bp.route('/edit_post/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_post(id):
    post = db.get_or_404(Post, id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.body = form.post.data
        post.category = form.category.data
        post.custom_category = form.custom_category.data.strip() if form.category.data == "other" and form.custom_category.data else None
        db.session.commit()
        flash('Your post has been updated.')
        return redirect(url_for('main.user', username=current_user.username))
    elif request.method == 'GET':
        form.post.data = post.body
        form.category.data = post.category
        form.custom_category.data = post.custom_category
    return render_template('edit_post.html', title='Edit Post', form=form)

@bp.route('/delete_post/<int:id>', methods=['POST'])
@login_required
def delete_post(id):
    post = db.get_or_404(Post, id)
    if post.author != current_user and not current_user.is_admin:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted.')
    return redirect(url_for('main.user', username=current_user.username))

from app.main.forms import CommentForm, EmptyForm

@bp.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('main.explore'))

    page = request.args.get('page', 1, type=int)
    q = g.search_form.q.data
    category = g.search_form.category.data

    posts_query, total = Post.search(q, page, current_app.config['POSTS_PER_PAGE'])
    posts = list(posts_query)
    if category:
        posts = [post for post in posts if post.category == category]

    next_url = url_for('main.search', q=q, category=category, page=page + 1) if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('main.search', q=q, category=category, page=page - 1) if page > 1 else None

    delete_form = EmptyForm()
    comment_form = CommentForm()  # <== add this

    return render_template(
        'search.html',
        title='Search',
        posts=posts,
        next_url=next_url,
        prev_url=prev_url,
        delete_form=delete_form,
        comment_form=comment_form  # <== AND pass it here
    )


@bp.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    form = CommentForm()
    post = db.get_or_404(Post, post_id)
    if form.validate_on_submit():
        parent_id = form.parent_id.data
        comment = Comment(
            body=form.body.data,
            author=current_user,
            post=post,
            parent_id=int(parent_id) if parent_id else None
        )
        db.session.add(comment)
        db.session.commit()
        flash('Comment posted!')
    return redirect(url_for('main.index'))
