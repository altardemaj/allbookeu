from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import db, User, BusinessOwner, Business, Service

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

        if not all([owner_name, email, password, biz_name, category, city, state]):
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

        owner = BusinessOwner(name=owner_name, email=email, business_id=business.id)
        owner.set_password(password)
        db.session.add(owner)
        db.session.commit()

        session.clear()
        session['user_id'] = owner.id
        session['user_type'] = 'owner'
        session['user_name'] = owner.name
        return redirect(url_for('biz.dashboard'))

    return render_template('auth/biz_signup.html', categories=categories)


@auth.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))
