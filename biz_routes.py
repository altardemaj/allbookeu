from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, BusinessOwner, Business, Booking, Service, RestaurantTable, Shift
from datetime import date, timedelta, datetime
import json
import cloudinary
import cloudinary.uploader

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


def _safe_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


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


def assign_table_for_booking(business, booking_day, booking_time, party_size):
    tables = RestaurantTable.query.filter_by(business_id=business.id, is_active=True).all()
    if not tables:
        existing = Booking.query.filter_by(
            business_id=business.id,
            booking_date=booking_day,
            booking_time=booking_time,
            status='confirmed'
        ).first()
        return None, existing is None

    for table in sorted(tables, key=lambda x: x.capacity):
        if table.capacity >= party_size and not table.is_booked_at(booking_day, booking_time):
            return table.id, True
    return None, False


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

    profile_fields = [
        business.name,
        business.cuisine,
        business.description,
        business.address,
        business.city,
        business.country,
        business.phone,
    ]
    default_cover_marker = 'photo-1556742049-0cfed4f6a45d'
    has_custom_cover = bool(business.image_url and default_cover_marker not in business.image_url)
    has_hours_or_shifts = bool(business.get_hours_display()) or Shift.query.filter_by(business_id=business.id).count() > 0
    has_floor_plan = any(t.grid_x is not None and t.grid_y is not None for t in tables)
    has_test_booking = Booking.query.filter_by(business_id=business.id).first() is not None
    onboarding_items = [
        {
            'key': 'profile',
            'label_key': 'onboarding_profile_completed',
            'helper_key': 'onboarding_profile_helper',
            'done': all(bool(str(v).strip()) for v in profile_fields),
            'href': url_for('biz.profile'),
            'action_key': 'onboarding_profile_action',
        },
        {
            'key': 'cover',
            'label_key': 'onboarding_cover_uploaded',
            'helper_key': 'onboarding_cover_helper',
            'done': has_custom_cover,
            'href': url_for('biz.profile'),
            'action_key': 'onboarding_cover_action',
        },
        {
            'key': 'hours',
            'label_key': 'onboarding_hours_added',
            'helper_key': 'onboarding_hours_helper',
            'done': has_hours_or_shifts,
            'href': url_for('biz.shifts'),
            'action_key': 'onboarding_hours_action',
        },
        {
            'key': 'tables',
            'label_key': 'onboarding_tables_created',
            'helper_key': 'onboarding_tables_helper',
            'done': len(tables) > 0,
            'href': url_for('biz.tables'),
            'action_key': 'onboarding_tables_action',
        },
        {
            'key': 'floor',
            'label_key': 'onboarding_floor_configured',
            'helper_key': 'onboarding_floor_helper',
            'done': has_floor_plan,
            'href': url_for('biz.floor_builder'),
            'action_key': 'onboarding_floor_action',
        },
        {
            'key': 'booking',
            'label_key': 'onboarding_test_booking_created',
            'helper_key': 'onboarding_test_booking_helper',
            'done': has_test_booking,
            'href': url_for('biz.new_booking'),
            'action_key': 'onboarding_test_booking_action',
        },
    ]
    onboarding_done = sum(1 for item in onboarding_items if item['done'])
    onboarding_total = len(onboarding_items)
    onboarding_progress = round(onboarding_done / onboarding_total * 100) if onboarding_total else 0

    # Covers (party size totals)
    today_covers = sum(b.party_size for b in today_bookings)
    week_covers = sum(b.party_size for b in week_bookings)

    # Last week comparison
    last_week_start = today - timedelta(days=today.weekday() + 7)
    last_week_end = last_week_start + timedelta(days=7)
    last_week_bookings_q = Booking.query.filter(
        Booking.business_id == business.id,
        Booking.booking_date >= last_week_start,
        Booking.booking_date < last_week_end,
        Booking.status != 'cancelled'
    ).all()
    last_week_covers = sum(b.party_size for b in last_week_bookings_q)

    # Same day last week
    same_day_last_week = Booking.query.filter(
        Booking.business_id == business.id,
        Booking.booking_date == today - timedelta(days=7),
        Booking.status != 'cancelled'
    ).all()
    same_day_covers = sum(b.party_size for b in same_day_last_week)

    def _pct_change(new, old):
        if old == 0:
            return None
        return round((new - old) / old * 100)

    today_covers_change = _pct_change(today_covers, same_day_covers)
    week_covers_change = _pct_change(week_covers, last_week_covers)

    # 14-day bar chart data (today and 13 days back)
    chart_days = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        day_bs = Booking.query.filter(
            Booking.business_id == business.id,
            Booking.booking_date == d,
            Booking.status != 'cancelled'
        ).all()
        chart_days.append({
            'label': d.strftime('%a') if i % 7 == 0 or i == 0 else d.strftime('%d'),
            'date': d.strftime('%b %d'),
            'covers': sum(b.party_size for b in day_bs),
            'bookings': len(day_bs),
            'is_today': d == today,
            'is_this_week': i < 7,
        })
    max_covers = max((d['covers'] for d in chart_days), default=1) or 1

    return render_template('biz/dashboard.html',
                           owner=owner, business=business,
                           today_bookings=today_bookings,
                           week_bookings=week_bookings,
                           calendar_days=calendar_days,
                           total_bookings=total_bookings,
                           total_customers=total_customers,
                           table_status=table_status,
                           today=today,
                           onboarding_items=onboarding_items,
                           onboarding_done=onboarding_done,
                           onboarding_total=onboarding_total,
                           onboarding_progress=onboarding_progress,
                           today_covers=today_covers,
                           week_covers=week_covers,
                           last_week_covers=last_week_covers,
                           today_covers_change=today_covers_change,
                           week_covers_change=week_covers_change,
                           chart_days=chart_days,
                           max_covers=max_covers)


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


@biz.route('/reservations')
@owner_required
def reservations_redirect():
    return redirect(url_for('biz.bookings'))


@biz.route('/bookings/new', methods=['GET', 'POST'])
@owner_required
def new_booking():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    today = date.today()

    def render_form():
        return render_template('biz/booking_form.html', owner=owner, business=business,
                               time_options=TIME_OPTIONS, today=today,
                               form_values=request.form)

    if request.method == 'POST':
        name = request.form.get('customer_name', '').strip()
        phone = request.form.get('customer_phone', '').strip()
        email = request.form.get('customer_email', '').strip()
        booking_date_raw = request.form.get('booking_date', '').strip()
        booking_time = request.form.get('booking_time', '').strip()
        notes = request.form.get('notes', '').strip()
        source = request.form.get('source', 'Phone').strip() or 'Phone'

        try:
            party_size = int(request.form.get('party_size', 2))
        except (TypeError, ValueError):
            party_size = 2

        try:
            booking_day = datetime.strptime(booking_date_raw, '%Y-%m-%d').date()
        except ValueError:
            booking_day = None

        if not name or not phone or not booking_day or not booking_time:
            flash('Guest name, phone, date, and time are required.', 'error')
            return render_form()

        if booking_day < today:
            flash('Choose today or a future date for this reservation.', 'error')
            return render_form()

        if party_size < 1 or party_size > 30:
            flash('Party size must be between 1 and 30 guests.', 'error')
            return render_form()

        table_id, has_capacity = assign_table_for_booking(business, booking_day, booking_time, party_size)
        if not has_capacity:
            flash('No table is available for that party size and time.', 'error')
            return render_form()

        stored_email = email or f"phone-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}@phone.allbookeu.local"
        booking_notes = f"{source} reservation"
        if notes:
            booking_notes = f"{booking_notes}: {notes}"

        booking = Booking(
            business_id=business.id,
            user_id=None,
            table_id=table_id,
            customer_name=name,
            customer_email=stored_email,
            customer_phone=phone,
            booking_date=booking_day,
            booking_time=booking_time,
            party_size=party_size,
            notes=booking_notes,
            status='confirmed'
        )
        db.session.add(booking)
        db.session.commit()

        flash(f'Reservation added for {name}.', 'success')
        return redirect(url_for('biz.bookings', date=booking_day.isoformat()))

    return render_form()


@biz.route('/booking/<int:booking_id>/status', methods=['POST'])
@owner_required
def update_booking_status(booking_id):
    owner, business = get_owner_business()
    booking = Booking.query.get_or_404(booking_id)
    if booking.business_id != business.id:
        return jsonify({'error': 'Unauthorized'}), 403

    new_status = request.form.get('status')
    if new_status in ('confirmed', 'cancelled', 'completed', 'seated'):
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


@biz.route('/flow-controls', methods=['GET', 'POST'])
@owner_required
def flow_controls():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    if request.method == 'POST':
        business.max_reservations_per_slot = _safe_int(
            request.form.get('max_reservations_per_slot'),
            default=0,
            minimum=0,
            maximum=100
        )
        business.max_guests_per_slot = _safe_int(
            request.form.get('max_guests_per_slot'),
            default=0,
            minimum=0,
            maximum=500
        )

        interval = _safe_int(request.form.get('booking_interval_minutes'), default=30)
        business.booking_interval_minutes = interval if interval in (15, 30, 60) else 30

        business.booking_buffer_minutes = _safe_int(
            request.form.get('booking_buffer_minutes'),
            default=0,
            minimum=0,
            maximum=240
        )
        business.booking_lead_time_minutes = _safe_int(
            request.form.get('booking_lead_time_minutes'),
            default=0,
            minimum=0,
            maximum=1440
        )

        business.reservations_paused = request.form.get('reservations_paused') == 'on'
        pause_message = request.form.get('pause_message', '').strip()
        business.pause_message = pause_message or 'Reservations are temporarily paused. Please call us to book.'

        db.session.commit()
        flash('Reservation flow controls updated.', 'success')
        return redirect(url_for('biz.flow_controls'))

    defaults = {
        'max_reservations_per_slot': 0,
        'max_guests_per_slot': 0,
        'booking_interval_minutes': 30,
        'booking_buffer_minutes': 0,
        'booking_lead_time_minutes': 0,
    }
    current = {
        key: getattr(business, key, value) if getattr(business, key, None) is not None else value
        for key, value in defaults.items()
    }

    return render_template('biz/flow_controls.html',
                           owner=owner,
                           business=business,
                           current=current)


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
            capacity = _safe_int(request.form.get('capacity'), default=4, minimum=1, maximum=30)
            section = request.form.get('section_custom', '').strip() or request.form.get('section', 'Main Floor').strip()
            notes = request.form.get('notes', '').strip()
            shape = request.form.get('shape', 'square').strip()
            if shape not in ('square', 'round', 'rect'):
                shape = 'square'
            if table_number:
                t = RestaurantTable(
                    business_id=business.id,
                    table_number=table_number,
                    capacity=capacity,
                    section=section,
                    notes=notes,
                    shape=shape,
                    is_active=request.form.get('is_active') == 'on'
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
                t.capacity = _safe_int(request.form.get('capacity'), default=t.capacity, minimum=1, maximum=30)
                t.section = request.form.get('section_custom', '').strip() or request.form.get('section', t.section).strip()
                t.notes = request.form.get('notes', '').strip()
                t.is_active = request.form.get('is_active') == 'on'
                new_shape = request.form.get('shape', t.shape or 'square').strip()
                if new_shape in ('square', 'round', 'rect'):
                    t.shape = new_shape
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

    known_sections = list(dict.fromkeys(SECTIONS + [t.section for t in all_tables if t.section]))
    hint_section = request.args.get('hint_section', '').strip()
    if hint_section and hint_section not in known_sections:
        known_sections.append(hint_section)

    return render_template('biz/tables.html', owner=owner, business=business,
                           all_tables=all_tables, sections_map=sections_map,
                           sections=known_sections, hint_section=hint_section)


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
            cover_file = request.files.get('cover_photo')
            if cover_file and cover_file.filename:
                try:
                    result = cloudinary.uploader.unsigned_upload(
                        cover_file,
                        'allbookeu',
                        cloud_name='dclrp75ux'
                    )
                    business.image_url = result['secure_url']
                except Exception as e:
                    flash(f'Image upload failed: {e}', 'error')
            else:
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
        elif b.status == 'seated':
            minutes = 0
            if bt:
                bt_dt = datetime.combine(selected_date, bt)
                minutes = max(0, int((now_dt - bt_dt).total_seconds() / 60))
            seated.append({'booking': b, 'minutes': minutes})
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
            elif booking.status == 'seated':
                status = 'seated'
                if bt:
                    bt_dt = datetime.combine(selected_date, bt)
                    minutes_seated = max(0, int((now_dt - bt_dt).total_seconds() / 60))
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


DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
SHIFT_COLORS = ['#1d4ed8', '#7c3aed', '#065f46', '#92400e', '#1e3a5f', '#3b0764', '#134e4a']


@biz.route('/shifts', methods=['GET', 'POST'])
@owner_required
def shifts():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            name = request.form.get('name', '').strip()
            days = ','.join(request.form.getlist('days'))
            start_time = request.form.get('start_time', '12:00')
            end_time = request.form.get('end_time', '22:00')
            slot_min = int(request.form.get('slot_minutes', 30))
            if not name or not days:
                flash('Shift name and at least one day are required.', 'error')
            elif start_time >= end_time:
                flash('End time must be after start time.', 'error')
            else:
                s = Shift(business_id=business.id, name=name, days=days,
                          start_time=start_time, end_time=end_time, slot_minutes=slot_min)
                db.session.add(s)
                db.session.commit()
                flash(f'Shift "{name}" added.', 'success')

        elif action == 'edit':
            shift_id = int(request.form.get('shift_id', 0))
            s = Shift.query.get(shift_id)
            if s and s.business_id == business.id:
                s.name = request.form.get('name', s.name).strip()
                days = ','.join(request.form.getlist('days'))
                s.days = days if days else s.days
                s.start_time = request.form.get('start_time', s.start_time)
                s.end_time = request.form.get('end_time', s.end_time)
                s.slot_minutes = int(request.form.get('slot_minutes', s.slot_minutes))
                if s.start_time >= s.end_time:
                    flash('End time must be after start time.', 'error')
                else:
                    db.session.commit()
                    flash(f'Shift "{s.name}" updated.', 'success')

        elif action == 'toggle':
            shift_id = int(request.form.get('shift_id', 0))
            s = Shift.query.get(shift_id)
            if s and s.business_id == business.id:
                s.is_active = not s.is_active
                db.session.commit()
                flash(f'Shift "{s.name}" {"activated" if s.is_active else "paused"}.', 'success')

        elif action == 'delete':
            shift_id = int(request.form.get('shift_id', 0))
            s = Shift.query.get(shift_id)
            if s and s.business_id == business.id:
                db.session.delete(s)
                db.session.commit()
                flash('Shift removed.', 'success')

        return redirect(url_for('biz.shifts'))

    all_shifts = Shift.query.filter_by(business_id=business.id).order_by(Shift.start_time).all()

    # Assign a color to each shift
    shifts_with_color = []
    for i, s in enumerate(all_shifts):
        shifts_with_color.append({'shift': s, 'color': SHIFT_COLORS[i % len(SHIFT_COLORS)]})

    # Build weekly grid: 7 days × list of shifts active that day
    grid = {d: [] for d in range(7)}
    for item in shifts_with_color:
        s = item['shift']
        for d in s.get_days_list():
            grid[d].append(item)

    return render_template('biz/shifts.html',
                           owner=owner, business=business,
                           all_shifts=all_shifts,
                           shifts_with_color=shifts_with_color,
                           grid=grid,
                           day_labels=DAY_LABELS,
                           current_dow=date.today().weekday(),
                           today=date.today())


@biz.route('/floor-builder')
@owner_required
def floor_builder():
    owner, business = get_owner_business()
    if not business:
        return redirect(url_for('biz.dashboard'))

    all_tables = RestaurantTable.query.filter_by(
        business_id=business.id, is_active=True
    ).order_by(RestaurantTable.section, RestaurantTable.table_number).all()

    # All unique sections in insertion order
    all_sections = list(dict.fromkeys(t.section for t in all_tables)) or ['Main Floor']

    current_section = request.args.get('section', all_sections[0])
    if current_section not in all_sections:
        current_section = all_sections[0]

    # Only tables in the current section
    section_tables = [t for t in all_tables if t.section == current_section]
    placed = [t for t in section_tables if t.grid_x is not None and t.grid_y is not None]
    unplaced = [t for t in section_tables if t.grid_x is None or t.grid_y is None]

    return render_template('biz/floor_builder.html',
                           owner=owner, business=business,
                           placed=placed, unplaced=unplaced,
                           all_tables=all_tables,
                           all_sections=all_sections,
                           current_section=current_section,
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

    # Check for collision within the same section only
    conflict = RestaurantTable.query.filter_by(
        business_id=business.id, section=t.section, grid_x=x, grid_y=y
    ).filter(RestaurantTable.id != table_id).first()
    if conflict:
        return jsonify({'error': 'Cell occupied', 'by': conflict.table_number}), 409

    t.grid_x = x
    t.grid_y = y
    db.session.commit()
    return jsonify({'ok': True, 'x': x, 'y': y})



@biz.route('/floor/assign', methods=['POST'])
@owner_required
def floor_assign():
    owner, business = get_owner_business()
    data = request.get_json()
    booking_id = data.get('booking_id')
    table_id = data.get('table_id')
    action = data.get('action', 'seat')  # seat | unassign | finish

    booking = Booking.query.get_or_404(booking_id)
    if booking.business_id != business.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if action == 'seat':
        booking.table_id = table_id
        booking.status = 'seated'
    elif action == 'unassign':
        booking.table_id = None
        booking.status = 'confirmed'
    elif action == 'finish':
        booking.status = 'completed'

    db.session.commit()
    return jsonify({'ok': True, 'booking_id': booking_id, 'status': booking.status})


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
