from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, Admin, BusinessOwner, Business, Booking, User, Review
from datetime import date, timedelta

admin = Blueprint('admin', __name__, url_prefix='/admin')


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

    # Recent bookings (last 7 days)
    recent = Booking.query.filter(
        Booking.booking_date >= today - timedelta(days=7),
        Booking.status != 'cancelled'
    ).order_by(Booking.created_at.desc()).limit(10).all()

    # Chart: bookings per day last 14 days
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

    owners = BusinessOwner.query
    if status_filter != 'all':
        owners = owners.filter_by(status=status_filter)
    owners = owners.order_by(BusinessOwner.created_at.desc()).all()

    if q:
        owners = [o for o in owners if q.lower() in o.name.lower() or q.lower() in o.email.lower()
                  or (o.business and q.lower() in o.business.name.lower())]

    return render_template('admin/restaurants.html', owners=owners, status_filter=status_filter, q=q)


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
            base_url = os.environ.get('BASE_URL', 'https://allbookeu.vercel.app')
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
    today = date.today()
    date_filter = request.args.get('date', '')
    restaurant_filter = request.args.get('restaurant', '')
    status_filter = request.args.get('status', 'all')
    q = request.args.get('q', '').strip()

    bookings_q = Booking.query
    if status_filter != 'all':
        bookings_q = bookings_q.filter_by(status=status_filter)
    if date_filter:
        try:
            from datetime import datetime
            bookings_q = bookings_q.filter_by(booking_date=datetime.strptime(date_filter, '%Y-%m-%d').date())
        except ValueError:
            pass
    if restaurant_filter:
        bookings_q = bookings_q.filter_by(business_id=int(restaurant_filter))
    if q:
        bookings_q = bookings_q.filter(
            Booking.customer_name.ilike(f'%{q}%') | Booking.customer_email.ilike(f'%{q}%')
        )

    all_bookings = bookings_q.order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).limit(200).all()
    all_restaurants = Business.query.order_by(Business.name).all()

    return render_template('admin/bookings.html',
                           bookings=all_bookings, restaurants=all_restaurants,
                           date_filter=date_filter, restaurant_filter=restaurant_filter,
                           status_filter=status_filter, q=q, today=today)


@admin.route('/featured/<int:business_id>', methods=['POST'])
@admin_required
def toggle_featured(business_id):
    b = Business.query.get_or_404(business_id)
    b.is_featured = not b.is_featured
    db.session.commit()
    return jsonify({'featured': b.is_featured})


@admin.route('/setup')
def setup():
    """One-time setup: create first admin. Disabled once any admin exists."""
    if Admin.query.count() > 0:
        return 'Admin already exists.', 403
    name = request.args.get('name', 'Admin')
    email = request.args.get('email')
    password = request.args.get('password')
    if not email or not password:
        return 'Pass ?email=&password= in the URL (one time only).', 400
    a = Admin(name=name, email=email)
    a.set_password(password)
    db.session.add(a)
    db.session.commit()
    return f'Admin created: {email}. Delete this route or protect it now.'
