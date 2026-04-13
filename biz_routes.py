from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, BusinessOwner, Business, Booking, Service
from datetime import date, timedelta
import json

biz = Blueprint('biz', __name__, url_prefix='/biz')

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


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') != 'owner':
            return redirect(url_for('auth.login', tab='owner'))
        return f(*args, **kwargs)
    return decorated


def get_owner_business():
    owner = BusinessOwner.query.get(session['user_id'])
    if not owner or not owner.business_id:
        return None, None
    return owner, Business.query.get(owner.business_id)


@biz.route('/dashboard')
@owner_required
def dashboard():
    owner, business = get_owner_business()
    if not business:
        flash('No business found. Please complete your profile.', 'error')
        return redirect(url_for('biz.profile'))

    today = date.today()
    today_bookings = business.today_bookings()
    week_bookings = business.week_bookings()

    # Build upcoming 7-day calendar data
    calendar_days = []
    for i in range(7):
        day = today + timedelta(days=i)
        day_bookings = [b for b in week_bookings if b.booking_date == day]
        calendar_days.append({
            'date': day,
            'display': day.strftime('%a'),
            'full': day.strftime('%b %d'),
            'bookings': day_bookings,
            'is_today': day == today
        })

    total_bookings = Booking.query.filter_by(business_id=business.id)\
        .filter(Booking.status != 'cancelled').count()
    total_customers = db.session.query(Booking.customer_email)\
        .filter_by(business_id=business.id)\
        .filter(Booking.status != 'cancelled')\
        .distinct().count()

    return render_template('biz/dashboard.html',
                           owner=owner, business=business,
                           today_bookings=today_bookings,
                           week_bookings=week_bookings,
                           calendar_days=calendar_days,
                           total_bookings=total_bookings,
                           total_customers=total_customers,
                           today=today)


@biz.route('/bookings')
@owner_required
def bookings():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    status_filter = request.args.get('status', 'all')
    date_filter = request.args.get('date', '')

    query = Booking.query.filter_by(business_id=business.id)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if date_filter:
        try:
            from datetime import datetime
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter_by(booking_date=filter_date)
        except ValueError:
            pass

    all_bookings = query.order_by(Booking.booking_date.desc(), Booking.booking_time).all()
    return render_template('biz/bookings.html', owner=owner, business=business,
                           bookings=all_bookings, status_filter=status_filter,
                           date_filter=date_filter)


@biz.route('/booking/<int:booking_id>/status', methods=['POST'])
@owner_required
def update_booking_status(booking_id):
    owner, business = get_owner_business()
    booking = Booking.query.get_or_404(booking_id)
    if booking.business_id != business.id:
        return jsonify({'error': 'Unauthorized'}), 403

    new_status = request.form.get('status')
    if new_status in ('confirmed', 'cancelled', 'completed'):
        booking.status = new_status
        db.session.commit()
        flash(f'Booking #{booking.id} marked as {new_status}.', 'success')
    return redirect(url_for('biz.bookings'))


@biz.route('/services', methods=['GET', 'POST'])
@owner_required
def services():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            duration = int(request.form.get('duration_minutes', 60))
            price = float(request.form.get('price', 0))
            if name:
                svc = Service(business_id=business.id, name=name,
                              description=description, duration_minutes=duration, price=price)
                db.session.add(svc)
                db.session.commit()
                flash(f'Service "{name}" added.', 'success')
            else:
                flash('Service name is required.', 'error')

        elif action == 'edit':
            svc_id = int(request.form.get('service_id', 0))
            svc = Service.query.get(svc_id)
            if svc and svc.business_id == business.id:
                svc.name = request.form.get('name', svc.name).strip()
                svc.description = request.form.get('description', '').strip()
                svc.duration_minutes = int(request.form.get('duration_minutes', 60))
                svc.price = float(request.form.get('price', 0))
                db.session.commit()
                flash('Service updated.', 'success')

        elif action == 'delete':
            svc_id = int(request.form.get('service_id', 0))
            svc = Service.query.get(svc_id)
            if svc and svc.business_id == business.id:
                db.session.delete(svc)
                db.session.commit()
                flash('Service removed.', 'success')

        return redirect(url_for('biz.services'))

    all_services = Service.query.filter_by(business_id=business.id, is_active=True)\
        .order_by(Service.created_at).all()
    return render_template('biz/services.html', owner=owner, business=business,
                           services=all_services)


@biz.route('/profile', methods=['GET', 'POST'])
@owner_required
def profile():
    owner, business = get_owner_business()
    if not business:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            business.name = request.form.get('name', business.name).strip()
            business.description = request.form.get('description', '').strip()
            business.address = request.form.get('address', '').strip()
            business.city = request.form.get('city', '').strip()
            business.state = request.form.get('state', '').strip()
            business.zip_code = request.form.get('zip_code', '').strip()
            business.phone = request.form.get('phone', '').strip()
            business.email = request.form.get('biz_email', '').strip()
            business.website = request.form.get('website', '').strip()
            business.price_range = request.form.get('price_range', '$$')
            img = request.form.get('image_url', '').strip()
            if img:
                business.image_url = img
            db.session.commit()
            flash('Business profile updated.', 'success')

        elif action == 'update_hours':
            hours = {}
            for day in DAYS:
                closed = request.form.get(f'closed_{day}')
                if closed:
                    hours[day] = 'closed'
                else:
                    open_t = request.form.get(f'open_{day}', '9:00 AM')
                    close_t = request.form.get(f'close_{day}', '6:00 PM')
                    hours[day] = f"{open_t} – {close_t}"
            business.hours = json.dumps(hours)
            db.session.commit()
            flash('Hours updated.', 'success')

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not owner.check_password(current_pw):
                flash('Current password is incorrect.', 'error')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
            elif new_pw != confirm_pw:
                flash('Passwords do not match.', 'error')
            else:
                owner.set_password(new_pw)
                db.session.commit()
                flash('Password updated.', 'success')

        return redirect(url_for('biz.profile'))

    hours_data = business.get_hours_display()
    return render_template('biz/profile.html', owner=owner, business=business,
                           hours_data=hours_data, days=DAYS, day_names=DAY_NAMES,
                           time_options=TIME_OPTIONS)
