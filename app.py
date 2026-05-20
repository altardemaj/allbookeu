from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort
from database import db, Business, Booking, Review, User, BusinessOwner, Service, RestaurantTable, Shift, Admin
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import hmac
import os
import secrets
import time
from translations import get_translation

load_dotenv()

app = Flask(__name__)
_db_url = os.environ.get('NEON_DATABASE_URL') or os.environ.get('DATABASE_URL', 'sqlite:///allbook.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-secret')

db.init_app(app)

_RATE_LIMITS = {
    'auth.login': (10, 15 * 60),
    'admin.login': (8, 15 * 60),
    'auth.signup': (5, 60 * 60),
    'auth.biz_signup': (4, 60 * 60),
    'auth.forgot_password': (3, 60 * 60),
    'book': (8, 10 * 60),
}
_RATE_LIMIT_BUCKETS = {}


def _client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _rate_limit_response(retry_after):
    if request.is_json or request.endpoint == 'book':
        response = jsonify({
            'success': False,
            'error': 'Too many attempts. Please wait a few minutes and try again.'
        })
        response.status_code = 429
        response.headers['Retry-After'] = str(retry_after)
        return response
    return render_template('errors/429.html', retry_after=retry_after), 429, {'Retry-After': str(retry_after)}


def get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.before_request
def protect_post_requests():
    if request.method != 'POST':
        return
    if request.endpoint in {'setup', 'admin.setup'}:
        return
    expected = session.get('_csrf_token')
    provided = (
        request.headers.get('X-CSRF-Token')
        or request.form.get('_csrf_token')
        or ((request.get_json(silent=True) or {}).get('_csrf_token') if request.is_json else None)
    )
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        abort(400)


@app.before_request
def rate_limit_sensitive_posts():
    if request.method != 'POST':
        return
    limit_config = _RATE_LIMITS.get(request.endpoint)
    if not limit_config:
        return

    max_attempts, window_seconds = limit_config
    now = time.time()
    key = (request.endpoint, _client_ip())
    attempts = [
        attempt for attempt in _RATE_LIMIT_BUCKETS.get(key, [])
        if now - attempt < window_seconds
    ]

    if len(attempts) >= max_attempts:
        retry_after = max(1, int(window_seconds - (now - attempts[0])))
        _RATE_LIMIT_BUCKETS[key] = attempts
        return _rate_limit_response(retry_after)

    attempts.append(now)
    _RATE_LIMIT_BUCKETS[key] = attempts

def _migrate_db():
    from sqlalchemy import text, inspect
    new_cols = [
        ("restaurant_tables", "grid_x", "INTEGER"),
        ("restaurant_tables", "grid_y", "INTEGER"),
        ("users", "reset_token", "VARCHAR(100)"),
        ("users", "reset_token_expires", "TIMESTAMP"),
        ("business_owners", "reset_token", "VARCHAR(100)"),
        ("business_owners", "reset_token_expires", "TIMESTAMP"),
        ("business_owners", "status", "VARCHAR(20) DEFAULT 'active'"),
        ("reviews", "user_id", "INTEGER"),
        ("restaurant_tables", "shape", "VARCHAR(20) DEFAULT 'square'"),
        ("businesses", "max_reservations_per_slot", "INTEGER DEFAULT 0"),
        ("businesses", "max_guests_per_slot", "INTEGER DEFAULT 0"),
        ("businesses", "booking_interval_minutes", "INTEGER DEFAULT 30"),
        ("businesses", "booking_buffer_minutes", "INTEGER DEFAULT 0"),
        ("businesses", "booking_lead_time_minutes", "INTEGER DEFAULT 0"),
    ]
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        for table, col, dtype in new_cols:
            if table not in existing_tables:
                continue
            current_inspector = inspect(db.engine)
            existing = [c['name'] for c in current_inspector.get_columns(table)]
            if col not in existing:
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}"))

from auth_routes import auth
from customer_routes import customer
from biz_routes import biz
from admin_routes import admin as admin_bp
app.register_blueprint(auth)
app.register_blueprint(customer)
app.register_blueprint(biz)
app.register_blueprint(admin_bp)

# Run migrations automatically on every cold start (idempotent — uses IF NOT EXISTS)
try:
    _migrate_db()
except Exception:
    pass

KOSOVO_CITIES = ['Prishtina', 'Prizren', 'Peja', 'Gjakova', 'Ferizaj', 'Gjilan', 'Mitrovica', 'Vushtrri', 'Podujeva', 'Suhareka']
ALBANIA_CITIES = ['Tirana', 'Durrës', 'Shkodër', 'Vlorë', 'Elbasan', 'Fier', 'Korçë', 'Berat', 'Sarandë', 'Lushnja']

CUISINES = [
    'Albanian', 'Italian', 'Mediterranean', 'Grill & BBQ',
    'Seafood', 'Traditional Kosovan', 'International', 'Pizza',
    'Fast Food', 'Cafe & Bistro', 'Sushi', 'Turkish'
]


@app.context_processor
def inject_auth():
    current_user = None
    current_owner = None
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    if user_type == 'customer' and user_id:
        current_user = User.query.get(user_id)
    elif user_type == 'owner' and user_id:
        current_owner = BusinessOwner.query.get(user_id)
    lang = session.get('lang', 'sq')
    def t(key):
        return get_translation(lang, key)
    return dict(
        current_user=current_user,
        current_owner=current_owner,
        user_type=user_type,
        kosovo_cities=KOSOVO_CITIES,
        albania_cities=ALBANIA_CITIES,
        all_cuisines=CUISINES,
        lang=lang,
        t=t,
        csrf_token=get_csrf_token,
    )


@app.route('/')
def index():
    try:
        featured = Business.query.filter_by(is_featured=True, category='restaurant').limit(8).all()
        cities_data = []
        for city in ['Prishtina', 'Prizren', 'Tirana', 'Durrës', 'Peja', 'Gjakova']:
            count = Business.query.filter_by(city=city, category='restaurant').count()
            cities_data.append({'name': city, 'count': count})
    except Exception:
        featured = []
        cities_data = []
    return render_template('index.html', featured=featured, cities=cities_data, cuisines=CUISINES)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    city = request.args.get('city', '').strip()
    cuisine = request.args.get('cuisine', '').strip()
    country = request.args.get('country', '').strip()
    date_str = request.args.get('date', '').strip()
    time_str = request.args.get('time', '').strip()
    party_str = request.args.get('party', '2').strip()

    businesses = Business.query.filter_by(category='restaurant')
    if query:
        businesses = businesses.filter(
            Business.name.ilike(f'%{query}%') |
            Business.description.ilike(f'%{query}%') |
            Business.cuisine.ilike(f'%{query}%')
        )
    if city:
        businesses = businesses.filter_by(city=city)
    if country:
        businesses = businesses.filter_by(country=country)
    if cuisine:
        businesses = businesses.filter_by(cuisine=cuisine)

    businesses = businesses.all()

    search_date = date.today()
    try:
        if date_str:
            search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        search_date = date.today()

    try:
        party_size = max(1, min(20, int(party_str)))
    except (TypeError, ValueError):
        party_size = 2
        party_str = '2'

    availability_map = {}
    for b in businesses:
        availability_map[b.id] = [] if b.reservations_paused else b.get_available_times(search_date, party_size)

    if date_str and time_str:
        try:
            available = []
            for b in businesses:
                if time_str in availability_map.get(b.id, []):
                    available.append(b)
            businesses = available
        except (TypeError, ValueError):
            pass

    all_cities = KOSOVO_CITIES + ALBANIA_CITIES

    return render_template('search.html',
                           businesses=businesses,
                           query=query,
                           city=city,
                           cuisine=cuisine,
                           country=country,
                           date_str=date_str,
                           time_str=time_str,
                           party_str=party_str,
                           search_date=search_date,
                           availability_map=availability_map,
                           all_cities=all_cities,
                           cuisines=CUISINES)


@app.route('/restaurant/<int:business_id>')
def business_detail(business_id):
    business = Business.query.get_or_404(business_id)
    reviews = Review.query.filter_by(business_id=business_id)\
        .order_by(Review.created_at.desc()).all()

    pre_date = request.args.get('date', '')
    pre_time = request.args.get('time', '')
    pre_party = request.args.get('party', '2')
    try:
        pre_party_size = max(1, int(pre_party))
    except (TypeError, ValueError):
        pre_party_size = 2

    slots = []
    today = date.today()
    for i in range(14):
        day = today + timedelta(days=i)
        slots.append({
            'date': day.strftime('%Y-%m-%d'),
            'display': day.strftime('%a, %b %d'),
            'full_display': day.strftime('%A, %B %d'),
            'short_day': day.strftime('%a'),
            'short_date': day.strftime('%b %d'),
            'is_today': day == today,
            'times': business.get_available_times(day, pre_party_size) if not business.reservations_paused else []
        })

    prefill = {}
    if session.get('user_type') == 'customer':
        user = User.query.get(session.get('user_id'))
        if user:
            prefill = {'name': user.name, 'email': user.email, 'phone': user.phone or ''}

    return render_template('business.html',
                           business=business,
                           reviews=reviews,
                           slots=slots,
                           prefill=prefill,
                           pre_date=pre_date,
                           pre_time=pre_time,
                           pre_party=pre_party)


@app.route('/book', methods=['POST'])
def book():
    data = request.get_json(silent=True) or {}
    business_id = data.get('business_id')
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    booking_date = data.get('date')
    booking_time = data.get('time')
    party_size_raw = data.get('party_size', 2)
    notes = data.get('notes', '')

    if not all([business_id, name, email, booking_date, booking_time]):
        return jsonify({'success': False, 'error': 'Please fill in all required fields.'}), 400

    try:
        party_size = int(party_size_raw)
        if party_size < 1 or party_size > 20:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Please choose a valid party size.'}), 400

    try:
        booking_day = datetime.strptime(booking_date, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Please choose a valid reservation date.'}), 400

    if booking_day < date.today():
        return jsonify({'success': False, 'error': 'Please choose a future reservation date.'}), 400

    business = Business.query.get(business_id)
    if not business:
        return jsonify({'success': False, 'error': 'Restaurant not found.'}), 404

    if business.reservations_paused:
        return jsonify({'success': False, 'error': business.pause_message or 'Reservations are paused.'}), 400

    if booking_time not in business.get_available_times(booking_day, party_size):
        return jsonify({'success': False, 'error': 'That time is no longer available. Please choose another time.'}), 409

    user_id = None
    if session.get('user_type') == 'customer':
        user_id = session.get('user_id')

    table_id = None
    tables = RestaurantTable.query.filter_by(business_id=business_id, is_active=True).all()
    if tables:
        for t in sorted(tables, key=lambda x: x.capacity):
            if t.capacity >= party_size and business.table_available_for_time(t, booking_day, booking_time):
                table_id = t.id
                break
        if table_id is None:
            return jsonify({'success': False, 'error': 'No table is available for that party size and time.'}), 409

    booking = Booking(
        business_id=business_id,
        user_id=user_id,
        table_id=table_id,
        customer_name=name,
        customer_email=email,
        customer_phone=phone,
        booking_date=booking_day,
        booking_time=booking_time,
        party_size=party_size,
        notes=notes,
        status='confirmed'
    )
    db.session.add(booking)
    db.session.commit()

    table_info = ''
    if table_id:
        t = RestaurantTable.query.get(table_id)
        table_info = f'{t.section} – Table {t.table_number}'

    try:
        from email_utils import send_booking_confirmation, send_new_booking_alert
        send_booking_confirmation(booking, business)
        owner = BusinessOwner.query.filter_by(business_id=business.id).first()
        if owner:
            send_new_booking_alert(booking, business, owner.email)
    except Exception:
        pass

    return jsonify({
        'success': True,
        'booking_id': booking.id,
        'table_info': table_info,
        'restaurant_name': business.name,
        'restaurant_phone': business.phone or '',
        'restaurant_email': business.email or '',
        'date': booking_date,
        'time': booking_time,
        'party_size': party_size,
        'message': f'Reservation confirmed at {business.name} on {booking_date} at {booking_time}!'
    })


@app.route('/lang/<code>')
def set_language(code):
    if code in ('sq', 'en'):
        session['lang'] = code
    return redirect(request.referrer or url_for('index'))


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('errors/500.html'), 500


@app.errorhandler(429)
def too_many_requests(error):
    return render_template('errors/429.html'), 429


@app.route('/setup', methods=['POST'])
def setup():
    setup_token = os.environ.get('ADMIN_SETUP_TOKEN')
    provided_token = request.headers.get('X-Setup-Token') or request.form.get('token') or request.args.get('token')
    if not setup_token or not provided_token or not hmac.compare_digest(setup_token, provided_token):
        return 'Not found', 404
    try:
        _migrate_db()
        if request.form.get('seed') == '1' or request.args.get('seed') == '1':
            seed_data()
        biz_count = Business.query.count()
        return f'OK - {biz_count} restaurants in DB.'
    except Exception as e:
        return f'Error: {e}', 500


@app.route('/api/restaurant/<int:business_id>/availability')
def api_restaurant_availability(business_id):
    business = Business.query.get_or_404(business_id)
    try:
        party_size = max(1, min(20, int(request.args.get('party', 2))))
    except (TypeError, ValueError):
        party_size = 2

    today = date.today()
    slots = []
    for i in range(14):
        day = today + timedelta(days=i)
        times = business.get_available_times(day, party_size) if not business.reservations_paused else []
        slots.append({
            'date': day.strftime('%Y-%m-%d'),
            'display': day.strftime('%a, %b %d'),
            'full_display': day.strftime('%A, %B %d'),
            'short_day': day.strftime('%a'),
            'short_date': day.strftime('%b %d'),
            'is_today': day == today,
            'times': times,
            'available_count': len(times)
        })
    return jsonify({
        'success': True,
        'slots': slots,
        'reservations_paused': business.reservations_paused,
        'pause_message': business.pause_message or ''
    })


@app.route('/api/businesses')
def api_businesses():
    city = request.args.get('city')
    cuisine = request.args.get('cuisine')
    q = request.args.get('q', '')
    businesses = Business.query.filter_by(category='restaurant')
    if city:
        businesses = businesses.filter_by(city=city)
    if cuisine:
        businesses = businesses.filter_by(cuisine=cuisine)
    if q:
        businesses = businesses.filter(Business.name.ilike(f'%{q}%'))
    result = [b.to_dict() for b in businesses.limit(20).all()]
    return jsonify(result)


def seed_data():
    if Business.query.count() > 0:
        return

    restaurants = [
        # PRISHTINA, KOSOVO
        Business(name="Soma Book Station", category="restaurant", cuisine="Cafe & Bistro",
                 description="Prishtina's most beloved all-day cafe and bistro. Artisan coffee, fresh pastries, and a curated menu in a cozy book-lined setting.",
                 address="Rr. Sejdi Kryeziu 9", city="Prishtina", country="Kosovo",
                 phone="+383 44 111 001", email="info@soma.ks",
                 rating=4.9, review_count=412, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"8am-10pm","tue":"8am-10pm","wed":"8am-10pm","thu":"8am-11pm","fri":"8am-11pm","sat":"9am-11pm","sun":"10am-9pm"}'),
        Business(name="Tiffany Restaurant", category="restaurant", cuisine="Mediterranean",
                 description="Elegant Mediterranean cuisine in the heart of Prishtina. Fresh seafood, grilled meats, and fine wines in a sophisticated atmosphere.",
                 address="Rr. UCK 181", city="Prishtina", country="Kosovo",
                 phone="+383 44 111 002", email="reservations@tiffany.ks",
                 rating=4.7, review_count=284, price_range="€€€",
                 image_url="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"12pm-11pm","tue":"12pm-11pm","wed":"12pm-11pm","thu":"12pm-midnight","fri":"12pm-midnight","sat":"12pm-midnight","sun":"1pm-10pm"}'),
        Business(name="Piazza Restaurant", category="restaurant", cuisine="Italian",
                 description="Authentic Italian flavors brought to Kosovo. Wood-fired pizzas, fresh pasta, and tiramisu made from traditional family recipes.",
                 address="Sheshi Nena Tereze", city="Prishtina", country="Kosovo",
                 phone="+383 44 111 003", email="info@piazza.ks",
                 rating=4.6, review_count=198, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"11am-11pm","tue":"11am-11pm","wed":"11am-11pm","thu":"11am-midnight","fri":"11am-midnight","sat":"11am-midnight","sun":"12pm-10pm"}'),
        Business(name="Liburnia Restaurant", category="restaurant", cuisine="Traditional Kosovan",
                 description="A celebration of Kosovo's rich culinary heritage. Traditional recipes passed down through generations — tavë kosi, flija, and grilled lamb.",
                 address="Rr. Garibaldi 22", city="Prishtina", country="Kosovo",
                 phone="+383 44 111 004", email="info@liburnia.ks",
                 rating=4.8, review_count=356, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"11am-10pm","tue":"11am-10pm","wed":"11am-10pm","thu":"11am-11pm","fri":"11am-11pm","sat":"11am-11pm","sun":"12pm-10pm"}'),
        # PRIZREN, KOSOVO
        Business(name="Mrizi i Zanave Prizren", category="restaurant", cuisine="Traditional Kosovan",
                 description="Stone-walled restaurant inside Prizren's old bazaar. Slow-cooked meats, wild herbs, and homemade bread baked in a clay oven.",
                 address="Rruga e Kalasë 5", city="Prizren", country="Kosovo",
                 phone="+383 44 222 001", email="info@mriziprizren.ks",
                 rating=4.9, review_count=503, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1559339352-11d035aa65de?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"10am-11pm","tue":"10am-11pm","wed":"10am-11pm","thu":"10am-midnight","fri":"10am-midnight","sat":"10am-midnight","sun":"11am-10pm"}'),
        Business(name="Shtepia e Vjetër", category="restaurant", cuisine="Albanian",
                 description="Perched above the Bistrica river with views of Prizren fortress. Albanian cuisine served in a 19th-century Ottoman house.",
                 address="Rr. Remzi Ademi 3", city="Prizren", country="Kosovo",
                 phone="+383 44 222 002", email="info@shtepiavjeter.ks",
                 rating=4.7, review_count=219, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&q=80",
                 is_featured=False,
                 hours='{"mon":"11am-10pm","tue":"11am-10pm","wed":"11am-10pm","thu":"11am-11pm","fri":"11am-11pm","sat":"11am-11pm","sun":"12pm-9pm"}'),
        # PEJA, KOSOVO
        Business(name="Te Peja Restaurant", category="restaurant", cuisine="Grill & BBQ",
                 description="Famous for Peja's legendary grilled meats. The qebapa and shish here have won awards at every regional food festival.",
                 address="Rr. Mbretëreshës 10", city="Peja", country="Kosovo",
                 phone="+383 44 333 001", email="info@tepeja.ks",
                 rating=4.8, review_count=388, price_range="€",
                 image_url="https://images.unsplash.com/photo-1544025162-d76694265947?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"10am-11pm","tue":"10am-11pm","wed":"10am-11pm","thu":"10am-midnight","fri":"10am-midnight","sat":"10am-midnight","sun":"11am-10pm"}'),
        # GJAKOVA, KOSOVO
        Business(name="Gjarperi Restaurant", category="restaurant", cuisine="Traditional Kosovan",
                 description="Gjakova's most storied restaurant, serving traditional Kosovan fare in a historic setting for over 30 years.",
                 address="Çarshia e Madhe 14", city="Gjakova", country="Kosovo",
                 phone="+383 44 444 001", email="info@gjarperi.ks",
                 rating=4.6, review_count=267, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1424847651672-bf20a4b0982b?w=600&q=80",
                 is_featured=False,
                 hours='{"mon":"11am-10pm","tue":"11am-10pm","wed":"11am-10pm","thu":"11am-11pm","fri":"11am-11pm","sat":"11am-11pm","sun":"12pm-9pm"}'),
        # TIRANA, ALBANIA
        Business(name="Mullixhiu", category="restaurant", cuisine="Albanian",
                 description="Tirana's most celebrated fine dining destination. Chef Bledar Kola elevates traditional Albanian ingredients into extraordinary modern cuisine.",
                 address="Rr. Sami Frashëri, Parku Rinia", city="Tirana", country="Albania",
                 phone="+355 69 111 001", email="reservations@mullixhiu.al",
                 rating=4.9, review_count=621, price_range="€€€€",
                 image_url="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"closed","tue":"12pm-11pm","wed":"12pm-11pm","thu":"12pm-11pm","fri":"12pm-midnight","sat":"12pm-midnight","sun":"12pm-10pm"}'),
        Business(name="Oda Restaurant", category="restaurant", cuisine="Albanian",
                 description="A cultural institution in Tirana serving traditional Albanian and Kosovan dishes in a beautiful Ottoman-style setting.",
                 address="Rr. Luigi Gurakuqi 12", city="Tirana", country="Albania",
                 phone="+355 69 111 002", email="info@oda.al",
                 rating=4.7, review_count=445, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1559339352-11d035aa65de?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"11am-11pm","tue":"11am-11pm","wed":"11am-11pm","thu":"11am-11pm","fri":"11am-midnight","sat":"11am-midnight","sun":"12pm-10pm"}'),
        Business(name="Blloku Social Club", category="restaurant", cuisine="International",
                 description="The heart of Tirana's trendy Blloku district. International menu, craft cocktails, and electric atmosphere from brunch to late night.",
                 address="Rr. Pjetër Bogdani 7, Blloku", city="Tirana", country="Albania",
                 phone="+355 69 111 003", email="info@blloku.al",
                 rating=4.5, review_count=312, price_range="€€€",
                 image_url="https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"9am-midnight","tue":"9am-midnight","wed":"9am-midnight","thu":"9am-1am","fri":"9am-2am","sat":"10am-2am","sun":"10am-midnight"}'),
        # DURRËS, ALBANIA
        Business(name="Plazhi i Ri Seafood", category="restaurant", cuisine="Seafood",
                 description="Fresh-caught Adriatic seafood served on the beach. Grilled fish, lobster, and mussels paired with cold local wine.",
                 address="Rr. Taulantia, Plazhi", city="Durrës", country="Albania",
                 phone="+355 69 222 001", email="info@plazhi.al",
                 rating=4.8, review_count=534, price_range="€€€",
                 image_url="https://images.unsplash.com/photo-1432139555190-58524dae6a55?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"12pm-11pm","tue":"12pm-11pm","wed":"12pm-11pm","thu":"12pm-11pm","fri":"12pm-midnight","sat":"11am-midnight","sun":"11am-11pm"}'),
        # SHKODËR, ALBANIA
        Business(name="Tradita Restaurant", category="restaurant", cuisine="Albanian",
                 description="An ode to northern Albanian tradition. Rustic interiors, open hearth cooking, and the finest gjellë e zezë in the country.",
                 address="Rr. Edith Durham 3", city="Shkodër", country="Albania",
                 phone="+355 69 333 001", email="info@tradita.al",
                 rating=4.8, review_count=289, price_range="€€",
                 image_url="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&q=80",
                 is_featured=False,
                 hours='{"mon":"11am-10pm","tue":"11am-10pm","wed":"11am-10pm","thu":"11am-11pm","fri":"11am-11pm","sat":"11am-11pm","sun":"12pm-9pm"}'),
        # VLORË, ALBANIA
        Business(name="Lungomare Restaurant", category="restaurant", cuisine="Seafood",
                 description="Spectacular promenade views over the Bay of Vlorë. Premium seafood, local wines, and sunsets that make every meal unforgettable.",
                 address="Lungomare Vlorë 45", city="Vlorë", country="Albania",
                 phone="+355 69 444 001", email="info@lungomare.al",
                 rating=4.7, review_count=367, price_range="€€€",
                 image_url="https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&q=80",
                 is_featured=True,
                 hours='{"mon":"12pm-11pm","tue":"12pm-11pm","wed":"12pm-11pm","thu":"12pm-11pm","fri":"12pm-midnight","sat":"11am-midnight","sun":"11am-11pm"}'),
    ]

    for r in restaurants:
        db.session.add(r)
    db.session.flush()

    reviews_data = [
        Review(business_id=1, reviewer_name="Arta K.", rating=5, comment="Best coffee in Prishtina, hands down. Love the atmosphere!"),
        Review(business_id=1, reviewer_name="Besnik M.", rating=5, comment="Came for brunch, stayed for hours. Incredible food and vibe."),
        Review(business_id=2, reviewer_name="Elena R.", rating=5, comment="The seafood pasta was exceptional. Will be back next week."),
        Review(business_id=3, reviewer_name="Valmir S.", rating=4, comment="Great pizza, very authentic Italian flavors."),
        Review(business_id=4, reviewer_name="Flutura H.", rating=5, comment="Tavë kosi here is the best I've ever had. Real home cooking."),
        Review(business_id=5, reviewer_name="Driton B.", rating=5, comment="The flija in the old bazaar setting — magical experience."),
        Review(business_id=7, reviewer_name="Kushtrim L.", rating=5, comment="The qebapa here are legendary. Worth the drive from Prishtina."),
        Review(business_id=9, reviewer_name="Mirela P.", rating=5, comment="Mullixhiu is in another league. Albania's finest table, full stop."),
        Review(business_id=10, reviewer_name="Arjan D.", rating=5, comment="The oda setting is beautiful and the food matches it perfectly."),
        Review(business_id=12, reviewer_name="Klaudia N.", rating=5, comment="Fresh fish straight from the Adriatic. Perfect seaside lunch."),
        Review(business_id=14, reviewer_name="Gjergji T.", rating=5, comment="The sunset from the terrace here is worth a trip alone."),
    ]
    for rv in reviews_data:
        db.session.add(rv)

    tables_data = [
        RestaurantTable(business_id=1, table_number="T1", capacity=2, section="Main Floor"),
        RestaurantTable(business_id=1, table_number="T2", capacity=2, section="Main Floor"),
        RestaurantTable(business_id=1, table_number="T3", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=1, table_number="T4", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=1, table_number="T5", capacity=6, section="Main Floor"),
        RestaurantTable(business_id=1, table_number="P1", capacity=2, section="Terrace"),
        RestaurantTable(business_id=1, table_number="P2", capacity=4, section="Terrace"),
        RestaurantTable(business_id=1, table_number="P3", capacity=4, section="Terrace"),
        RestaurantTable(business_id=2, table_number="T1", capacity=2, section="Main Floor"),
        RestaurantTable(business_id=2, table_number="T2", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=2, table_number="T3", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=2, table_number="T4", capacity=6, section="Main Floor"),
        RestaurantTable(business_id=2, table_number="R1", capacity=8, section="Private Room"),
        RestaurantTable(business_id=2, table_number="R2", capacity=12, section="Private Room"),
        RestaurantTable(business_id=9, table_number="T1", capacity=2, section="Main Floor"),
        RestaurantTable(business_id=9, table_number="T2", capacity=2, section="Main Floor"),
        RestaurantTable(business_id=9, table_number="T3", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=9, table_number="T4", capacity=4, section="Main Floor"),
        RestaurantTable(business_id=9, table_number="G1", capacity=6, section="Garden"),
        RestaurantTable(business_id=9, table_number="G2", capacity=8, section="Garden"),
    ]
    for t in tables_data:
        db.session.add(t)

    db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        _migrate_db()
        seed_data()
    app.run(debug=True, port=5000)
