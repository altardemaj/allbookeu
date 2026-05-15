from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import db, User, BusinessOwner, Business, Service
import secrets
from datetime import datetime, timedelta

auth = Blueprint('auth', __name__, url_prefix='/auth')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        account_type = request.form.get('account_type', 'customer')
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if account_type == 'owner':
            owner = BusinessOwner.query.filter_by(email=email).first()
            if owner and owner.check_password(password):
                if owner.status == 'pending':
                    flash('Your account is pending approval. We\'ll email you once it\'s approved.', 'info')
                    return render_template('auth/login.html', tab='owner')
                if owner.status == 'suspended':
                    flash('Your account has been suspended. Please contact support.', 'error')
                    return render_template('auth/login.html', tab='owner')
                session.clear()
                session['user_id'] = owner.id
                session['user_type'] = 'owner'
                session['user_name'] = owner.name
                return redirect(url_for('biz.dashboard'))
            flash('Invalid email or password.', 'error')
        else:
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                session.clear()
                session['user_id'] = user.id
                session['user_type'] = 'customer'
                session['user_name'] = user.name
                next_url = request.args.get('next')
                return redirect(next_url or url_for('customer.dashboard'))
            flash('Invalid email or password.', 'error')

    tab = request.args.get('tab', 'customer')
    return render_template('auth/login.html', tab=tab)


@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not name or not email or not password:
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/signup.html')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/signup.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/signup.html')
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('auth/signup.html')

        user = User(name=name, email=email, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session.clear()
        session['user_id'] = user.id
        session['user_type'] = 'customer'
        session['user_name'] = user.name
        return redirect(url_for('customer.dashboard'))

    return render_template('auth/signup.html')


@auth.route('/biz-signup', methods=['GET', 'POST'])
def biz_signup():
    from database import RESTAURANT_TIMES
    categories = [
        ('restaurant', 'Restaurant'),
        ('hair_salon', 'Hair Salon'),
        ('barbershop', 'Barbershop'),
        ('spa', 'Spa'),
        ('nail_salon', 'Nail Salon'),
        ('gym', 'Gym'),
    ]
    if request.method == 'POST':
        # Owner fields
        owner_name = request.form.get('owner_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        # Business fields
        biz_name = request.form.get('biz_name', '').strip()
        category = request.form.get('category', '')
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        zip_code = request.form.get('zip_code', '').strip()
        phone = request.form.get('phone', '').strip()
        biz_email = request.form.get('biz_email', '').strip()
        description = request.form.get('description', '').strip()

        if not all([owner_name, email, password, biz_name, city]):
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/biz_signup.html', categories=categories)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/biz_signup.html', categories=categories)
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/biz_signup.html', categories=categories)
        if BusinessOwner.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('auth/biz_signup.html', categories=categories)

        import json
        default_hours = json.dumps({
            'mon': '9am-6pm', 'tue': '9am-6pm', 'wed': '9am-6pm',
            'thu': '9am-6pm', 'fri': '9am-6pm', 'sat': '10am-4pm', 'sun': 'closed'
        })
        business = Business(
            name=biz_name, category=category, description=description,
            address=address, city=city, state=state, zip_code=zip_code,
            phone=phone, email=biz_email or email,
            rating=0.0, review_count=0, price_range='$$',
            image_url='https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=600&q=80',
            is_featured=False, hours=default_hours
        )
        db.session.add(business)
        db.session.flush()

        owner = BusinessOwner(name=owner_name, email=email, business_id=business.id, status='pending')
        owner.set_password(password)
        db.session.add(owner)
        db.session.commit()

        flash('Application submitted! We\'ll review it and email you within 24 hours.', 'info')
        return redirect(url_for('auth.login', tab='owner'))

    return render_template('auth/biz_signup.html', categories=categories)


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        account_type = request.form.get('account_type', 'customer')
        import os
        base_url = os.environ.get('BASE_URL', 'https://allbookeu.com').rstrip('/')
        if 'allbookeu.vercel.app' in base_url:
            base_url = 'https://allbookeu.com'

        if account_type == 'owner':
            user = BusinessOwner.query.filter_by(email=email).first()
            reset_route = 'auth.reset_password'
        else:
            user = User.query.filter_by(email=email).first()
            reset_route = 'auth.reset_password'

        if user:
            token = secrets.token_urlsafe(48)
            user.reset_token = token
            user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_url = f"{base_url}/auth/reset-password/{token}?type={account_type}"
            try:
                from email_utils import send_password_reset
                send_password_reset(email, user.name, reset_url, is_owner=(account_type == 'owner'))
            except Exception:
                pass

        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.forgot_password'))

    account_type = request.args.get('type', 'customer')
    return render_template('auth/forgot_password.html', account_type=account_type)


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    account_type = request.args.get('type', 'customer')

    if account_type == 'owner':
        user = BusinessOwner.query.filter_by(reset_token=token).first()
    else:
        user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/reset_password.html', token=token, account_type=account_type)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token, account_type=account_type)

        user.set_password(password)
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        flash('Password updated. Please log in.', 'success')
        return redirect(url_for('auth.login', tab=account_type))

    return render_template('auth/reset_password.html', token=token, account_type=account_type)


@auth.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))
