from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, BusinessOwner, Business, Booking, Service, RestaurantTable
from datetime import date, timedelta, datetime
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

SECTIONS = ['Main Floor', 'Terrace', 'Garden', 'Private Room', 'Bar', 'Rooftop', 'Basement']


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
        flash('No restaurant found. Please complete your profile.', 'error')
        return redirect(url_for('biz.profile'))

    today = date.today()
    today_bookings = business.today_bookings()
    week_bookings = business.week_bookings()

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

    tables = RestaurantTable.query.filter_by(business_id=business.id, is_active=True).all()
    table_status = []
    for t in tables:
        booked_times = [b.booking_time for b in today_bookings if b.table_id == t.id]
        table_status.append({
            'table': t,
            'booked_times': booked_times,
            'is_occupied': len(booked_times) > 0
        })

    return render_template('biz/dashboard.html',
                           owner=owner, business=business,
                           today_bookings=today_bookings,
                           week_bookings=week_bookings,
                           calendar_days=calendar_days,
                           total_bookings=total_bookings,
                           total_customers=total_customers,
                           table_status=table_status,
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
        flash(f'Reservation #{booking.id} marked as {new_status}.', 'success')
    return redirect(url_for('biz.bookings'))


@biz.route('/pause', methods=['POST'])
@owner_required
def toggle_pause():
    owner, business = get_owner_business()
    if not business:
        return jsonify({'error': 'No restaurant found'}), 404

    action = request.form.get('action')
    pause_message = request.form.get('pause_message', '').strip()

    if action == 'pause':
        business.reservations_paused = True
        business.pause_message = pause_message or 'Reservations are temporarily paused. Please call us to book.'
        db.session.commit()
        flash('Reservations are now paused. Guests will see a message when they try to book.', 'warning')
    elif action == 'resume':
        business.reservations_paused = False
        db.session.commit()
        flash('Reservations are open again. Guests can book online.', 'success')

    return redirect(request.referrer or url_for('biz.dashboard'))


@biz.route('/tables', methods=['GET', 'POST'])
@owner_required
def tables():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            table_number = request.form.get('table_number', '').strip()
            capacity = int(request.form.get('capacity', 4))
            section = request.form.get('section', 'Main Floor').strip()
            notes = request.form.get('notes', '').strip()
            if table_number:
                t = RestaurantTable(
                    business_id=business.id,
                    table_number=table_number,
                    capacity=capacity,
                    section=section,
                    notes=notes
                )
                db.session.add(t)
                db.session.commit()
                flash(f'Table {table_number} added to {section}.', 'success')
            else:
                flash('Table number is required.', 'error')

        elif action == 'edit':
            table_id = int(request.form.get('table_id', 0))
            t = RestaurantTable.query.get(table_id)
            if t and t.business_id == business.id:
                t.table_number = request.form.get('table_number', t.table_number).strip()
                t.capacity = int(request.form.get('capacity', t.capacity))
                t.section = request.form.get('section', t.section).strip()
                t.notes = request.form.get('notes', '').strip()
                db.session.commit()
                flash(f'Table {t.table_number} updated.', 'success')

        elif action == 'toggle':
            table_id = int(request.form.get('table_id', 0))
            t = RestaurantTable.query.get(table_id)
            if t and t.business_id == business.id:
                t.is_active = not t.is_active
                db.session.commit()
                status_word = 'activated' if t.is_active else 'deactivated'
                flash(f'Table {t.table_number} {status_word}.', 'success')

        elif action == 'delete':
            table_id = int(request.form.get('table_id', 0))
            t = RestaurantTable.query.get(table_id)
            if t and t.business_id == business.id:
                db.session.delete(t)
                db.session.commit()
                flash('Table removed.', 'success')

        return redirect(url_for('biz.tables'))

    all_tables = RestaurantTable.query.filter_by(business_id=business.id)\
        .order_by(RestaurantTable.section, RestaurantTable.table_number).all()

    sections_map = {}
    for t in all_tables:
        sections_map.setdefault(t.section, []).append(t)

    return render_template('biz/tables.html', owner=owner, business=business,
                           all_tables=all_tables, sections_map=sections_map,
                           sections=SECTIONS)


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
                flash(f'Menu item "{name}" added.', 'success')
            else:
                flash('Name is required.', 'error')

        elif action == 'edit':
            svc_id = int(request.form.get('service_id', 0))
            svc = Service.query.get(svc_id)
            if svc and svc.business_id == business.id:
                svc.name = request.form.get('name', svc.name).strip()
                svc.description = request.form.get('description', '').strip()
                svc.duration_minutes = int(request.form.get('duration_minutes', 60))
                svc.price = float(request.form.get('price', 0))
                db.session.commit()
                flash('Menu item updated.', 'success')

        elif action == 'delete':
            svc_id = int(request.form.get('service_id', 0))
            svc = Service.query.get(svc_id)
            if svc and svc.business_id == business.id:
                db.session.delete(svc)
                db.session.commit()
                flash('Menu item removed.', 'success')

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
            business.cuisine = request.form.get('cuisine', '').strip()
            business.description = request.form.get('description', '').strip()
            business.address = request.form.get('address', '').strip()
            business.city = request.form.get('city', '').strip()
            business.country = request.form.get('country', 'Kosovo').strip()
            business.phone = request.form.get('phone', '').strip()
            business.email = request.form.get('biz_email', '').strip()
            business.website = request.form.get('website', '').strip()
            business.price_range = request.form.get('price_range', '€€')
            img = request.form.get('image_url', '').strip()
            if img:
                business.image_url = img
            db.session.commit()
            flash('Restaurant profile updated.', 'success')

        elif action == 'update_hours':
            hours = {}
            for day in DAYS:
                closed = request.form.get(f'closed_{day}')
                if closed:
                    hours[day] = 'closed'
                else:
                    open_t = request.form.get(f'open_{day}', '9:00 AM')
                    close_t = request.form.get(f'close_{day}', '10:00 PM')
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

    from app import KOSOVO_CITIES, ALBANIA_CITIES, CUISINES
    hours_data = business.get_hours_display()
    return render_template('biz/profile.html', owner=owner, business=business,
                           hours_data=hours_data, days=DAYS, day_names=DAY_NAMES,
                           time_options=TIME_OPTIONS,
                           kosovo_cities=KOSOVO_CITIES,
                           albania_cities=ALBANIA_CITIES,
                           cuisines=CUISINES)


def _parse_booking_time(time_str):
    for fmt in ('%I:%M %p', '%I %p'):
        try:
            return datetime.strptime(time_str.strip(), fmt).time()
        except ValueError:
            continue
    return None


def _build_floor_data(business, selected_date):
    now_dt = datetime.now()
    now_time = now_dt.time()
    is_today = selected_date == date.today()

    day_bookings = Booking.query.filter_by(
        business_id=business.id,
        booking_date=selected_date
    ).filter(Booking.status != 'cancelled').order_by(Booking.booking_time).all()

    seated, upcoming, finished = [], [], []

    for b in day_bookings:
        bt = _parse_booking_time(b.booking_time)
        if b.status == 'completed' or selected_date < date.today():
            minutes = None
            if bt:
                bt_dt = datetime.combine(selected_date, bt)
                minutes = max(0, int((now_dt - bt_dt).total_seconds() / 60))
            finished.append({'booking': b, 'minutes': minutes})
        elif selected_date > date.today() or bt is None:
            upcoming.append({'booking': b, 'minutes_until': None})
        else:
            bt_dt = datetime.combine(date.today(), bt)
            diff = (now_dt - bt_dt).total_seconds() / 60
            if diff < 0:
                upcoming.append({'booking': b, 'minutes_until': int(-diff)})
            elif diff <= 135:
                seated.append({'booking': b, 'minutes': int(diff)})
            else:
                finished.append({'booking': b, 'minutes': int(diff)})

    table_booking_map = {b.table_id: b for b in day_bookings if b.table_id}

    all_tables = RestaurantTable.query.filter_by(
        business_id=business.id, is_active=True
    ).order_by(RestaurantTable.section, RestaurantTable.table_number).all()

    table_data = []
    for t in all_tables:
        booking = table_booking_map.get(t.id)
        status = 'available'
        minutes_seated = None
        minutes_until = None

        if booking:
            bt = _parse_booking_time(booking.booking_time)
            if booking.status == 'completed' or selected_date < date.today():
                status = 'finished'
            elif selected_date > date.today() or bt is None:
                status = 'upcoming'
            else:
                bt_dt = datetime.combine(date.today(), bt)
                diff = (now_dt - bt_dt).total_seconds() / 60
                if diff < 0:
                    status = 'upcoming'
                    minutes_until = int(-diff)
                elif diff <= 135:
                    status = 'seated'
                    minutes_seated = int(diff)
                else:
                    status = 'finished'

        table_data.append({
            'table': t,
            'booking': booking,
            'status': status,
            'minutes_seated': minutes_seated,
            'minutes_until': minutes_until,
        })

    sections_map = {}
    for td in table_data:
        sections_map.setdefault(td['table'].section, []).append(td)

    return {
        'day_bookings': day_bookings,
        'seated': seated,
        'upcoming': upcoming,
        'finished': finished,
        'sections_map': sections_map,
        'table_data': table_data,
    }


@biz.route('/floor')
@owner_required
def floor_view():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    date_str = request.args.get('date', '')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        selected_date = date.today()

    data = _build_floor_data(business, selected_date)
    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)

    return render_template('biz/floor.html',
                           owner=owner, business=business,
                           selected_date=selected_date,
                           today=date.today(),
                           prev_date=prev_date,
                           next_date=next_date,
                           **data)


@biz.route('/floor-builder')
@owner_required
def floor_builder():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    all_tables = RestaurantTable.query.filter_by(
        business_id=business.id, is_active=True
    ).order_by(RestaurantTable.section, RestaurantTable.table_number).all()

    placed = [t for t in all_tables if t.grid_x is not None and t.grid_y is not None]
    unplaced = [t for t in all_tables if t.grid_x is None or t.grid_y is None]

    # Build grid occupancy map for collision detection
    occupied = {(t.grid_x, t.grid_y): t for t in placed}

    return render_template('biz/floor_builder.html',
                           owner=owner, business=business,
                           placed=placed, unplaced=unplaced,
                           all_tables=all_tables,
                           occupied=occupied,
                           grid_cols=20, grid_rows=14)


@biz.route('/table/<int:table_id>/position', methods=['POST'])
@owner_required
def save_table_position(table_id):
    owner, business = get_owner_business()
    t = RestaurantTable.query.get_or_404(table_id)
    if t.business_id != business.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(force=True)
    x = data.get('x')
    y = data.get('y')

    # Clear position
    if x is None or y is None:
        t.grid_x = None
        t.grid_y = None
        db.session.commit()
        return jsonify({'ok': True})

    x, y = int(x), int(y)

    # Check for collision with another table
    conflict = RestaurantTable.query.filter_by(
        business_id=business.id, grid_x=x, grid_y=y
    ).filter(RestaurantTable.id != table_id).first()
    if conflict:
        return jsonify({'error': 'Cell occupied', 'by': conflict.table_number}), 409

    t.grid_x = x
    t.grid_y = y
    db.session.commit()
    return jsonify({'ok': True, 'x': x, 'y': y})


@biz.route('/floor/data')
@owner_required
def floor_data():
    owner, business = get_owner_business()
    if not business:
        return jsonify({'error': 'not found'}), 404

    date_str = request.args.get('date', '')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        selected_date = date.today()

    data = _build_floor_data(business, selected_date)

    tables_json = []
    for td in data['table_data']:
        t = td['table']
        b = td['booking']
        tables_json.append({
            'id': t.id,
            'number': t.table_number,
            'capacity': t.capacity,
            'section': t.section,
            'status': td['status'],
            'minutes_seated': td['minutes_seated'],
            'minutes_until': td['minutes_until'],
            'guest_name': b.customer_name if b else None,
            'party_size': b.party_size if b else None,
            'booking_time': b.booking_time if b else None,
        })

    return jsonify({
        'tables': tables_json,
        'seated_count': len(data['seated']),
        'upcoming_count': len(data['upcoming']),
    })
