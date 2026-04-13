from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from database import db, Business, Booking, Review, User, BusinessOwner, Service
from datetime import datetime, date, timedelta
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///allbook.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'allbook-secret-key-2024'

db.init_app(app)

# Register blueprints
from auth_routes import auth
from customer_routes import customer
from biz_routes import biz
app.register_blueprint(auth)
app.register_blueprint(customer)
app.register_blueprint(biz)

CATEGORIES = [
    {'id': 'restaurant', 'name': 'Restaurants', 'icon': '🍽️'},
    {'id': 'hair_salon', 'name': 'Hair Salons', 'icon': '✂️'},
    {'id': 'barbershop', 'name': 'Barbershops', 'icon': '💈'},
    {'id': 'spa', 'name': 'Spas', 'icon': '🧖'},
    {'id': 'nail_salon', 'name': 'Nail Salons', 'icon': '💅'},
    {'id': 'gym', 'name': 'Gyms', 'icon': '🏋️'},
]


@app.context_processor
def inject_auth():
    """Inject auth state into all templates."""
    current_user = None
    current_owner = None
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    if user_type == 'customer' and user_id:
        current_user = User.query.get(user_id)
    elif user_type == 'owner' and user_id:
        current_owner = BusinessOwner.query.get(user_id)
    return dict(
        current_user=current_user,
        current_owner=current_owner,
        user_type=user_type
    )


@app.route('/')
def index():
    featured = Business.query.filter_by(is_featured=True).limit(8).all()
    return render_template('index.html', featured=featured, categories=CATEGORIES)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    businesses = Business.query
    if query:
        businesses = businesses.filter(
            Business.name.ilike(f'%{query}%') |
            Business.description.ilike(f'%{query}%') |
            Business.city.ilike(f'%{query}%')
        )
    if category:
        businesses = businesses.filter_by(category=category)
    businesses = businesses.all()
    return render_template('search.html', businesses=businesses, query=query,
                           category=category, categories=CATEGORIES)


@app.route('/business/<int:business_id>')
def business_detail(business_id):
    business = Business.query.get_or_404(business_id)
    reviews = Review.query.filter_by(business_id=business_id)\
        .order_by(Review.created_at.desc()).all()
    slots = []
    today = date.today()
    for i in range(7):
        day = today + timedelta(days=i)
        slots.append({
            'date': day.strftime('%Y-%m-%d'),
            'display': day.strftime('%a, %b %d'),
            'times': business.get_available_times(day)
        })
    # Pre-fill customer info if logged in
    prefill = {}
    if session.get('user_type') == 'customer':
        user = User.query.get(session.get('user_id'))
        if user:
            prefill = {'name': user.name, 'email': user.email, 'phone': user.phone or ''}
    return render_template('business.html', business=business, reviews=reviews,
                           slots=slots, categories=CATEGORIES, prefill=prefill)


@app.route('/book', methods=['POST'])
def book():
    data = request.get_json()
    business_id = data.get('business_id')
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    booking_date = data.get('date')
    booking_time = data.get('time')
    party_size = data.get('party_size', 1)
    notes = data.get('notes', '')

    if not all([business_id, name, email, booking_date, booking_time]):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    business = Business.query.get(business_id)
    if not business:
        return jsonify({'success': False, 'error': 'Business not found'}), 404

    user_id = None
    if session.get('user_type') == 'customer':
        user_id = session.get('user_id')

    booking = Booking(
        business_id=business_id,
        user_id=user_id,
        customer_name=name,
        customer_email=email,
        customer_phone=phone,
        booking_date=datetime.strptime(booking_date, '%Y-%m-%d').date(),
        booking_time=booking_time,
        party_size=party_size,
        notes=notes,
        status='confirmed'
    )
    db.session.add(booking)
    db.session.commit()

    return jsonify({
        'success': True,
        'booking_id': booking.id,
        'message': f'Booking confirmed at {business.name} on {booking_date} at {booking_time}!'
    })


@app.route('/api/businesses')
def api_businesses():
    category = request.args.get('category')
    q = request.args.get('q', '')
    businesses = Business.query
    if category:
        businesses = businesses.filter_by(category=category)
    if q:
        businesses = businesses.filter(Business.name.ilike(f'%{q}%'))
    result = [b.to_dict() for b in businesses.limit(20).all()]
    return jsonify(result)


def seed_data():
    if Business.query.count() > 0:
        return
    sample_businesses = [
        Business(name="The Garden Table", category="restaurant",
                 description="Farm-to-table cuisine in a warm, inviting atmosphere. Seasonal menus crafted by James Beard nominated chef.",
                 address="124 Oak Street", city="New York", state="NY", zip_code="10001",
                 phone="(212) 555-0101", email="info@gardentable.com",
                 rating=4.8, review_count=312, price_range="$$$",
                 image_url="https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&q=80",
                 is_featured=True, hours='{"mon":"5pm-10pm","tue":"5pm-10pm","wed":"5pm-10pm","thu":"5pm-11pm","fri":"5pm-11pm","sat":"4pm-11pm","sun":"4pm-9pm"}'),
        Business(name="Luxe Hair Studio", category="hair_salon",
                 description="Award-winning hair salon offering cuts, color, and styling. Home to NYC's top colorists.",
                 address="88 5th Avenue", city="New York", state="NY", zip_code="10011",
                 phone="(212) 555-0202", email="book@luxehair.com",
                 rating=4.9, review_count=198, price_range="$$$",
                 image_url="https://images.unsplash.com/photo-1560066984-138dadb4c035?w=600&q=80",
                 is_featured=True, hours='{"mon":"9am-7pm","tue":"9am-7pm","wed":"9am-7pm","thu":"9am-8pm","fri":"9am-8pm","sat":"8am-6pm","sun":"closed"}'),
        Business(name="King's Barbershop", category="barbershop",
                 description="Classic cuts with a modern twist. Straight razor shaves and premium grooming in a vintage setting.",
                 address="33 West 14th St", city="New York", state="NY", zip_code="10011",
                 phone="(212) 555-0303", email="kings@barbershop.com",
                 rating=4.7, review_count=445, price_range="$$",
                 image_url="https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=600&q=80",
                 is_featured=True, hours='{"mon":"8am-8pm","tue":"8am-8pm","wed":"8am-8pm","thu":"8am-8pm","fri":"8am-9pm","sat":"7am-9pm","sun":"9am-5pm"}'),
        Business(name="Serenity Spa & Wellness", category="spa",
                 description="A tranquil escape in the heart of the city. Swedish massage, deep tissue, facials, and body treatments.",
                 address="205 Park Avenue", city="New York", state="NY", zip_code="10003",
                 phone="(212) 555-0404", email="relax@serenityspa.com",
                 rating=4.9, review_count=267, price_range="$$$$",
                 image_url="https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=600&q=80",
                 is_featured=True, hours='{"mon":"10am-8pm","tue":"10am-8pm","wed":"10am-8pm","thu":"10am-9pm","fri":"10am-9pm","sat":"9am-9pm","sun":"10am-7pm"}'),
        Business(name="Polished Nail Bar", category="nail_salon",
                 description="Luxury nail care with non-toxic polishes. Gel, acrylic, and organic treatments by certified technicians.",
                 address="67 Spring Street", city="New York", state="NY", zip_code="10012",
                 phone="(212) 555-0505", email="hello@polishednails.com",
                 rating=4.6, review_count=189, price_range="$$",
                 image_url="https://images.unsplash.com/photo-1604654894610-df63bc536371?w=600&q=80",
                 is_featured=True, hours='{"mon":"10am-7pm","tue":"10am-7pm","wed":"10am-7pm","thu":"10am-8pm","fri":"10am-8pm","sat":"9am-7pm","sun":"11am-6pm"}'),
        Business(name="Iron & Flow Fitness", category="gym",
                 description="Premium fitness studio with personal training, yoga, HIIT classes and state-of-the-art equipment.",
                 address="410 West 42nd St", city="New York", state="NY", zip_code="10036",
                 phone="(212) 555-0606", email="train@ironflow.com",
                 rating=4.8, review_count=523, price_range="$$$",
                 image_url="https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600&q=80",
                 is_featured=True, hours='{"mon":"5am-11pm","tue":"5am-11pm","wed":"5am-11pm","thu":"5am-11pm","fri":"5am-10pm","sat":"6am-9pm","sun":"7am-8pm"}'),
        Business(name="Sakura Japanese Kitchen", category="restaurant",
                 description="Authentic Japanese cuisine with omakase experience, fresh sushi bar, and handcrafted ramen.",
                 address="15 East 52nd St", city="New York", state="NY", zip_code="10022",
                 phone="(212) 555-0707", email="reserve@sakurakitchen.com",
                 rating=4.9, review_count=401, price_range="$$$$",
                 image_url="https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=600&q=80",
                 is_featured=True, hours='{"mon":"closed","tue":"5pm-10pm","wed":"5pm-10pm","thu":"5pm-10pm","fri":"5pm-11pm","sat":"12pm-11pm","sun":"12pm-9pm"}'),
        Business(name="Color & Co.", category="hair_salon",
                 description="Specialty color salon focused on balayage, highlights, and corrective color. Davines product line.",
                 address="112 Bleecker St", city="New York", state="NY", zip_code="10012",
                 phone="(212) 555-0808", email="color@colorandco.com",
                 rating=4.7, review_count=156, price_range="$$$",
                 image_url="https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=600&q=80",
                 is_featured=True, hours='{"mon":"closed","tue":"10am-7pm","wed":"10am-7pm","thu":"10am-8pm","fri":"10am-8pm","sat":"9am-6pm","sun":"closed"}'),
    ]
    for b in sample_businesses:
        db.session.add(b)
    db.session.flush()

    reviews_data = [
        Review(business_id=1, reviewer_name="Sarah M.", rating=5, comment="Absolutely stunning food and atmosphere."),
        Review(business_id=1, reviewer_name="James K.", rating=5, comment="Best farm-to-table in the city."),
        Review(business_id=2, reviewer_name="Emily R.", rating=5, comment="My colorist here is a wizard!"),
        Review(business_id=3, reviewer_name="Marcus T.", rating=5, comment="Best haircut I've had in years."),
        Review(business_id=4, reviewer_name="Amanda L.", rating=5, comment="Pure heaven. Incredibly professional staff."),
        Review(business_id=5, reviewer_name="Jessica W.", rating=5, comment="My nails lasted 3 weeks! Stunning nail art."),
        Review(business_id=6, reviewer_name="David C.", rating=5, comment="Personal training here is next level."),
        Review(business_id=7, reviewer_name="Priya S.", rating=5, comment="The omakase experience is unforgettable."),
        Review(business_id=8, reviewer_name="Nicole B.", rating=5, comment="Finally found my forever colorist!"),
    ]
    for r in reviews_data:
        db.session.add(r)

    # Seed services
    services_data = [
        Service(business_id=1, name="Dinner Reservation", duration_minutes=90, price=0, description="Reserve a table for dinner service"),
        Service(business_id=1, name="Private Dining Room", duration_minutes=180, price=500, description="Exclusive private room for special occasions"),
        Service(business_id=2, name="Haircut & Blowout", duration_minutes=60, price=120, description="Precision cut and professional blow dry"),
        Service(business_id=2, name="Full Color & Highlights", duration_minutes=150, price=280, description="Full color treatment or balayage highlights"),
        Service(business_id=3, name="Classic Haircut", duration_minutes=30, price=45, description="Scissor or clipper cut with style"),
        Service(business_id=3, name="Hot Towel Shave", duration_minutes=45, price=55, description="Traditional straight razor shave with hot towel"),
        Service(business_id=4, name="Swedish Massage (60 min)", duration_minutes=60, price=130, description="Full body relaxation massage"),
        Service(business_id=4, name="Deep Tissue Massage (90 min)", duration_minutes=90, price=185, description="Therapeutic deep tissue treatment"),
        Service(business_id=4, name="Signature Facial", duration_minutes=75, price=150, description="Custom facial tailored to your skin type"),
        Service(business_id=5, name="Gel Manicure", duration_minutes=60, price=55, description="Long-lasting gel polish manicure"),
        Service(business_id=5, name="Full Set Acrylics", duration_minutes=90, price=75, description="Full acrylic nail set with design"),
        Service(business_id=6, name="Personal Training Session", duration_minutes=60, price=95, description="One-on-one session with certified trainer"),
        Service(business_id=6, name="HIIT Class", duration_minutes=45, price=35, description="High-intensity interval training group class"),
        Service(business_id=7, name="Omakase Experience", duration_minutes=120, price=250, description="Chef's choice multi-course tasting menu"),
        Service(business_id=8, name="Balayage Color", duration_minutes=180, price=320, description="Hand-painted balayage for a natural look"),
    ]
    for s in services_data:
        db.session.add(s)

    db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Migrate existing bookings table: add user_id column if absent
        try:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE bookings ADD COLUMN user_id INTEGER REFERENCES users(id)'))
                conn.commit()
        except Exception:
            pass  # column already exists
        seed_data()
    app.run(debug=True, port=5000)
