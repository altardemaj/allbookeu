from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from database import db, User, Booking
from datetime import date

customer = Blueprint('customer', __name__, url_prefix='/customer')


def customer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') != 'customer':
            return redirect(url_for('auth.login', next=request.url, tab='customer'))
        return f(*args, **kwargs)
    return decorated


@customer.route('/dashboard')
@customer_required
def dashboard():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    upcoming = user.upcoming_bookings()
    past = user.past_bookings()
    return render_template('customer/dashboard.html', user=user,
                           upcoming=upcoming, past=past)


@customer.route('/cancel/<int:booking_id>', methods=['POST'])
@customer_required
def cancel_booking(booking_id):
    user = User.query.get(session['user_id'])
    booking = Booking.query.get_or_404(booking_id)

    # Verify this booking belongs to the logged-in user
    if booking.user_id != user.id and booking.customer_email != user.email:
        flash('You cannot cancel this booking.', 'error')
        return redirect(url_for('customer.dashboard'))

    if booking.booking_date < date.today():
        flash('Cannot cancel a past booking.', 'error')
        return redirect(url_for('customer.dashboard'))

    booking.status = 'cancelled'
    db.session.commit()
    flash('Booking cancelled successfully.', 'success')
    return redirect(url_for('customer.dashboard'))


@customer.route('/profile', methods=['GET', 'POST'])
@customer_required
def profile():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_profile':
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            if not name:
                flash('Name cannot be empty.', 'error')
            else:
                user.name = name
                user.phone = phone
                session['user_name'] = name
                db.session.commit()
                flash('Profile updated successfully.', 'success')

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not user.check_password(current_pw):
                flash('Current password is incorrect.', 'error')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'error')
            else:
                user.set_password(new_pw)
                db.session.commit()
                flash('Password changed successfully.', 'success')

        return redirect(url_for('customer.profile'))

    return render_template('customer/profile.html', user=user)
