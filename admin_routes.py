from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, Admin, BusinessOwner, Business, Booking, User, Review
from datetime import date, timedelta
import hmac
import json
import os

admin = Blueprint('admin', __name__, url_prefix='/admin')

DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
TIME_OPTIONS = [
    '6:00 AM','6:30 AM','7:00 AM','7:30 AM','8:00 AM','8:30 AM',
    '9:00 AM','9:30 AM','10:00 AM','10:30 AM','11:00 AM','11:30 AM',
    '12:00 PM','12:30 PM','1:00 PM','1:30 PM','2:00 PM','2:30 PM',
    '3:00 PM','3:30 PM','4:00 PM','4:30 PM','5:00 PM','5:30 PM',
    '6:00 PM','6:30 PM','7:00 PM','7:30 PM','8:00 PM','8:30 PM',
    '9:00 PM','9:30 PM','10:00 PM',
]


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') != 'admin':
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


@admin.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_type') == 'admin':
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        a = Admin.query.filter_by(email=email).first()
        if a and a.check_password(password):
            session.clear()
            session['user_id'] = a.id
            session['user_type'] = 'admin'
            session['user_name'] = a.name
            return redirect(url_for('admin.dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('admin/login.html')


@admin.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('admin.login'))


@admin.route('/')
@admin_required
def dashboard():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    stats = {
        'total_restaurants': Business.query.count(),
        'active_owners': BusinessOwner.query.filter_by(status='active').count(),
        'pending_owners': BusinessOwner.query.filter_by(status='pending').count(),
        'total_bookings': Booking.query.filter(Booking.status != 'cancelled').count(),
        'today_bookings': Booking.query.filter_by(booking_date=today).filter(Booking.status != 'cancelled').count(),
        'total_customers': db.session.query(Booking.customer_email).distinct().count(),
        'total_reviews': Review.query.count(),
    }

    pending = BusinessOwner.query.filter_by(status='pending').order_by(BusinessOwner.created_at.desc()).all()

    recent = Booking.query.filter(
        Booking.booking_date >= today - timedelta(days=7),
        Booking.status != 'cancelled'
    ).order_by(Booking.created_at.desc()).limit(10).all()

    chart = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        count = Booking.query.filter_by(booking_date=d).filter(Booking.status != 'cancelled').count()
        chart.append({'label': d.strftime('%b %d'), 'short': d.strftime('%d'), 'count': count, 'is_today': d == today})
    max_count = max((c['count'] for c in chart), default=1) or 1

    return render_template('admin/dashboard.html',
                           stats=stats, pending=pending,
                           recent=recent, chart=chart, max_count=max_count, today=today)


@admin.route('/restaurants')
@admin_required
def restaurants():
    status_filter = request.args.get('status', 'all')
    q = request.args.get('q', '').strip()

    businesses = Business.query.order_by(Business.created_at.desc()).all()

    if q:
        businesses = [b for b in businesses if
                      q.lower() in b.name.lower() or
                      q.lower() in (b.city or '').lower() or
                      (b.owner and (q.lower() in b.owner.name.lower() or
                                    q.lower() in b.owner.email.lower()))]

    if status_filter == 'pending':
        businesses = [b for b in businesses if b.owner and b.owner.status == 'pending']
    elif status_filter == 'active':
        businesses = [b for b in businesses if not b.owner or b.owner.status == 'active']
    elif status_filter == 'suspended':
        businesses = [b for b in businesses if b.owner and b.owner.status == 'suspended']

    return render_template('admin/restaurants.html', businesses=businesses,
                           status_filter=status_filter, q=q)


@admin.route('/restaurants/add', methods=['GET', 'POST'])
@admin_required
def add_restaurant():
    from app import KOSOVO_CITIES, ALBANIA_CITIES, CUISINES
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        cuisine = request.form.get('cuisine', '').strip()
        city = request.form.get('city', '').strip()
        country = request.form.get('country', 'Kosovo').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        biz_email = request.form.get('biz_email', '').strip()
        image_url = request.form.get('image_url', '').strip()
        price_range = request.form.get('price_range', '€€')
        description = request.form.get('description', '').strip()
        is_featured = bool(request.form.get('is_featured'))

        if not name or not city:
            flash('Name and city are required.', 'error')
            return render_template('admin/add_restaurant.html',
                                   kosovo_cities=KOSOVO_CITIES,
                                   albania_cities=ALBANIA_CITIES,
                                   cuisines=CUISINES)

        biz = Business(
            name=name, category='restaurant', cuisine=cuisine,
            city=city, country=country, address=address,
            phone=phone, email=biz_email,
            image_url=image_url or None,
            price_range=price_range, description=description,
            is_featured=is_featured
        )
        db.session.add(biz)
        db.session.commit()
        flash(f'Restaurant "{name}" added successfully.', 'success')
        return redirect(url_for('admin.restaurants'))

    return render_template('admin/add_restaurant.html',
                           kosovo_cities=KOSOVO_CITIES,
                           albania_cities=ALBANIA_CITIES,
                           cuisines=CUISINES)


@admin.route('/restaurants/<int:biz_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_restaurant(biz_id):
    from app import KOSOVO_CITIES, ALBANIA_CITIES, CUISINES
    biz = Business.query.get_or_404(biz_id)

    if request.method == 'POST':
        biz.name = request.form.get('name', biz.name).strip()
        biz.cuisine = request.form.get('cuisine', '').strip()
        biz.city = request.form.get('city', biz.city).strip()
        biz.country = request.form.get('country', 'Kosovo').strip()
        biz.address = request.form.get('address', '').strip()
        biz.phone = request.form.get('phone', '').strip()
        biz.email = request.form.get('biz_email', '').strip()
        img = request.form.get('image_url', '').strip()
        if img:
            biz.image_url = img
        biz.price_range = request.form.get('price_range', '€€')
        biz.description = request.form.get('description', '').strip()
        biz.is_featured = bool(request.form.get('is_featured'))

        # Hours
        hours = {}
        for day in DAYS:
            if request.form.get(f'closed_{day}'):
                hours[day] = 'closed'
            else:
                open_t = request.form.get(f'open_{day}', '9:00 AM')
                close_t = request.form.get(f'close_{day}', '10:00 PM')
                hours[day] = f"{open_t} – {close_t}"
        biz.hours = json.dumps(hours)

        db.session.commit()
        flash('Restaurant updated.', 'success')
        return redirect(url_for('admin.restaurants'))

    hours_data = biz.get_hours_display()
    return render_template('admin/edit_restaurant.html',
                           biz=biz,
                           hours_data=hours_data,
                           days=DAYS,
                           day_names=DAY_NAMES,
                           time_options=TIME_OPTIONS,
                           kosovo_cities=KOSOVO_CITIES,
                           albania_cities=ALBANIA_CITIES,
                           cuisines=CUISINES)


@admin.route('/restaurants/<int:biz_id>/delete', methods=['POST'])
@admin_required
def delete_business(biz_id):
    biz = Business.query.get_or_404(biz_id)
    name = biz.name
    # Delete owner if exists
    if biz.owner:
        db.session.delete(biz.owner)
    db.session.delete(biz)
    db.session.commit()
    flash(f'"{name}" deleted.', 'success')
    return redirect(url_for('admin.restaurants'))


@admin.route('/restaurants/<int:owner_id>/action', methods=['POST'])
@admin_required
def owner_action(owner_id):
    owner = BusinessOwner.query.get_or_404(owner_id)
    action = request.form.get('action')

    if action == 'approve':
        owner.status = 'active'
        db.session.commit()
        try:
            from email_utils import _send, _base
            import os
            base_url = os.environ.get('BASE_URL', 'https://allbookeu.com').rstrip('/')
            if 'vercel.app' in base_url:
                base_url = 'https://allbookeu.com'
            html = _base(f"""
            <h2 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#111">You're approved!</h2>
            <p style="margin:0 0 20px;color:#6b7280;font-size:15px">
              Hi {owner.name.split()[0]}, your restaurant <strong>{owner.business.name if owner.business else ''}</strong>
              has been approved on AllBookEU. You can now log in and start accepting reservations.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
              <a href="{base_url}/auth/login?tab=owner" style="display:inline-block;background:#e63946;color:#fff;font-size:14px;font-weight:700;padding:12px 28px;border-radius:6px;text-decoration:none">
                Go to Dashboard →
              </a>
            </td></tr></table>
            """, preheader='Your AllBookEU restaurant account is approved.')
            _send(owner.email, 'Your AllBookEU account is approved!', html)
        except Exception:
            pass
        flash(f'{owner.name} approved.', 'success')

    elif action == 'suspend':
        owner.status = 'suspended'
        db.session.commit()
        flash(f'{owner.name} suspended.', 'warning')

    elif action == 'reactivate':
        owner.status = 'active'
        db.session.commit()
        flash(f'{owner.name} reactivated.', 'success')

    elif action == 'delete':
        if owner.business:
            db.session.delete(owner.business)
        db.session.delete(owner)
        db.session.commit()
        flash('Restaurant and owner deleted.', 'success')

    return redirect(url_for('admin.restaurants'))


@admin.route('/bookings')
@admin_required
def bookings():
    q = request.args.get('q', '').strip()
    date_filter = request.args.get('date', '').strip()
    restaurant_filter = request.args.get('restaurant', '').strip()
    status_filter = request.args.get('status', 'all')

    query = Booking.query.order_by(Booking.booking_date.desc(), Booking.booking_time.desc())

    if status_filter != 'all':
        query = query.filter(Booking.status == status_filter)
    if restaurant_filter:
        query = query.filter(Booking.business_id == int(restaurant_filter))
    if date_filter:
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(Booking.booking_date == d)
        except ValueError:
            pass

    all_bookings = query.all()

    if q:
        all_bookings = [b for b in all_bookings if
                        q.lower() in b.customer_name.lower() or
                        q.lower() in b.customer_email.lower()]

    restaurants = Business.query.order_by(Business.name).all()
    return render_template('admin/bookings.html',
                           bookings=all_bookings,
                           q=q,
                           date_filter=date_filter,
                           restaurant_filter=restaurant_filter,
                           status_filter=status_filter,
                           restaurants=restaurants)


@admin.route('/reviews')
@admin_required
def reviews():
    all_reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin/reviews.html', reviews=all_reviews)


@admin.route('/reviews/<int:review_id>/delete', methods=['POST'])
@admin_required
def delete_review(review_id):
    r = Review.query.get_or_404(review_id)
    biz_id = r.business_id
    db.session.delete(r)
    db.session.flush()
    biz = Business.query.get(biz_id)
    remaining = Review.query.filter_by(business_id=biz_id).all()
    if remaining:
        biz.rating = round(sum(rv.rating for rv in remaining) / len(remaining), 1)
        biz.review_count = len(remaining)
    else:
        biz.rating = 0.0
        biz.review_count = 0
    db.session.commit()
    flash('Review deleted.', 'success')
    return redirect(url_for('admin.reviews'))


@admin.route('/featured/<int:business_id>', methods=['POST'])
@admin_required
def toggle_featured(business_id):
    b = Business.query.get_or_404(business_id)
    b.is_featured = not b.is_featured
    db.session.commit()
    return jsonify({'featured': b.is_featured})


@admin.route('/setup', methods=['POST'])
def setup():
    """Create the first admin account when protected by ADMIN_SETUP_TOKEN."""
    setup_token = os.environ.get('ADMIN_SETUP_TOKEN')
    provided_token = request.headers.get('X-Setup-Token') or request.form.get('token')
    if not setup_token or not provided_token or not hmac.compare_digest(setup_token, provided_token):
        return 'Not found', 404
    if Admin.query.count() > 0:
        return 'Admin already exists.', 403
    name = request.form.get('name', 'Admin')
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if not email or not password:
        return 'Email and password are required.', 400
    a = Admin(name=name, email=email)
    a.set_password(password)
    db.session.add(a)
    db.session.commit()
    return f'Admin created: {email}.'
