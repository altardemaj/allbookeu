from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

DEFAULT_TIMES = [
    "9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM",
    "12:00 PM", "12:30 PM", "1:00 PM", "1:30 PM", "2:00 PM", "2:30 PM",
    "3:00 PM", "3:30 PM", "4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM",
    "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM", "8:00 PM"
]

RESTAURANT_TIMES = [
    "11:30 AM", "12:00 PM", "12:30 PM", "1:00 PM", "1:30 PM",
    "5:00 PM", "5:30 PM", "6:00 PM", "6:30 PM", "7:00 PM",
    "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM"
]


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='user', lazy=True, foreign_keys='Booking.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def upcoming_bookings(self):
        return Booking.query.filter(
            (Booking.user_id == self.id) | (Booking.customer_email == self.email),
            Booking.booking_date >= date.today(),
            Booking.status == 'confirmed'
        ).order_by(Booking.booking_date, Booking.booking_time).all()

    def past_bookings(self):
        return Booking.query.filter(
            (Booking.user_id == self.id) | (Booking.customer_email == self.email),
            (Booking.booking_date < date.today()) | (Booking.status == 'cancelled')
        ).order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).all()


class BusinessOwner(db.Model):
    __tablename__ = 'business_owners'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    business = db.relationship('Business', backref='owner', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Business(db.Model):
    __tablename__ = 'businesses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    cuisine = db.Column(db.String(100))
    description = db.Column(db.Text)
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    country = db.Column(db.String(50), default='Kosovo')
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    website = db.Column(db.String(300))
    image_url = db.Column(db.String(500))
    rating = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)
    price_range = db.Column(db.String(10))
    hours = db.Column(db.Text)
    is_featured = db.Column(db.Boolean, default=False)
    reservations_paused = db.Column(db.Boolean, default=False)
    pause_message = db.Column(db.String(300), default='Reservations are temporarily paused.')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('Booking', backref='business', lazy=True)
    reviews = db.relationship('Review', backref='business', lazy=True)
    services = db.relationship('Service', backref='business', lazy=True)
    tables = db.relationship('RestaurantTable', backref='business', lazy=True,
                             order_by='RestaurantTable.section, RestaurantTable.table_number')
    shifts = db.relationship('Shift', backref='business', lazy=True,
                             order_by='Shift.start_time')

    def get_available_times(self, for_date):
        if self.reservations_paused:
            return []
        day_of_week = for_date.weekday()  # 0=Mon 6=Sun
        active_shifts = [s for s in self.shifts if s.is_active and day_of_week in s.get_days_list()]
        if active_shifts:
            seen = set()
            times = []
            for s in sorted(active_shifts, key=lambda x: x.start_time):
                for t in s.get_time_slots():
                    if t not in seen:
                        seen.add(t)
                        times.append(t)
        else:
            times = RESTAURANT_TIMES if self.category == 'restaurant' else DEFAULT_TIMES
        booked = {b.booking_time for b in self.bookings
                  if b.booking_date == for_date and b.status == 'confirmed'}
        return [t for t in times if t not in booked]

    def get_hours_display(self):
        if not self.hours:
            return {}
        try:
            return json.loads(self.hours)
        except Exception:
            return {}

    def today_bookings(self):
        return Booking.query.filter_by(
            business_id=self.id,
            booking_date=date.today()
        ).filter(Booking.status != 'cancelled').order_by(Booking.booking_time).all()

    def week_bookings(self):
        from datetime import timedelta
        start = date.today()
        end = start + timedelta(days=7)
        return Booking.query.filter(
            Booking.business_id == self.id,
            Booking.booking_date >= start,
            Booking.booking_date < end,
            Booking.status != 'cancelled'
        ).order_by(Booking.booking_date, Booking.booking_time).all()

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'cuisine': self.cuisine,
            'description': self.description,
            'city': self.city,
            'country': self.country,
            'rating': self.rating,
            'review_count': self.review_count,
            'price_range': self.price_range,
            'image_url': self.image_url,
        }


class RestaurantTable(db.Model):
    __tablename__ = 'restaurant_tables'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    table_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=4)
    section = db.Column(db.String(100), default='Main Floor')
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.String(200))
    grid_x = db.Column(db.Integer, nullable=True)
    grid_y = db.Column(db.Integer, nullable=True)

    bookings = db.relationship('Booking', backref='table', lazy=True, foreign_keys='Booking.table_id')

    def is_booked_at(self, check_date, check_time):
        return Booking.query.filter_by(
            table_id=self.id,
            booking_date=check_date,
            booking_time=check_time,
            status='confirmed'
        ).first() is not None


class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, default=60)
    price = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def duration_display(self):
        h = self.duration_minutes // 60
        m = self.duration_minutes % 60
        if h and m:
            return f"{h}h {m}m"
        elif h:
            return f"{h}h"
        return f"{m}m"


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    table_id = db.Column(db.Integer, db.ForeignKey('restaurant_tables.id'), nullable=True)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(30))
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.String(20), nullable=False)
    party_size = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='confirmed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_upcoming(self):
        return self.booking_date >= date.today() and self.status == 'confirmed'

    def date_display(self):
        return self.booking_date.strftime('%a, %b %d, %Y')


class Shift(db.Model):
    __tablename__ = 'shifts'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    days = db.Column(db.String(20), nullable=False, default='0,1,2,3,4,5,6')
    start_time = db.Column(db.String(5), nullable=False, default='09:00')
    end_time = db.Column(db.String(5), nullable=False, default='22:00')
    slot_minutes = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_days_list(self):
        return [int(d) for d in self.days.split(',') if d.strip().isdigit()]

    def get_time_slots(self):
        from datetime import timedelta as td
        slots = []
        try:
            sh, sm = map(int, self.start_time.split(':'))
            eh, em = map(int, self.end_time.split(':'))
        except Exception:
            return slots
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        cur = start_min
        while cur < end_min:
            h, m = divmod(cur, 60)
            ampm = 'AM' if h < 12 else 'PM'
            h12 = h % 12 or 12
            slots.append(f"{h12}:{m:02d} {ampm}")
            cur += self.slot_minutes
        return slots

    def start_display(self):
        try:
            h, m = map(int, self.start_time.split(':'))
            ampm = 'AM' if h < 12 else 'PM'
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {ampm}"
        except Exception:
            return self.start_time

    def end_display(self):
        try:
            h, m = map(int, self.end_time.split(':'))
            ampm = 'AM' if h < 12 else 'PM'
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {ampm}"
        except Exception:
            return self.end_time

    def start_minutes(self):
        try:
            h, m = map(int, self.start_time.split(':'))
            return h * 60 + m
        except Exception:
            return 0

    def duration_minutes(self):
        try:
            sh, sm = map(int, self.start_time.split(':'))
            eh, em = map(int, self.end_time.split(':'))
            return (eh * 60 + em) - (sh * 60 + sm)
        except Exception:
            return 0


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    reviewer_name = db.Column(db.String(200))
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
