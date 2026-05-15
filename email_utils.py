import os
import resend

resend.api_key = os.environ.get('RESEND_API_KEY', '')
SENDER = os.environ.get('EMAIL_FROM', 'AllBookEU <noreply@allbookeu.com>')
BASE_URL = os.environ.get('BASE_URL', 'https://allbookeu.com').rstrip('/')
if 'allbookeu.vercel.app' in BASE_URL:
    BASE_URL = 'https://allbookeu.com'

_RED = '#e63946'
_DARK = '#1a1a2e'


def _base(content_html, preheader=''):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AllBookEU</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
{'<div style="display:none;max-height:0;overflow:hidden;color:#f4f4f5">'+preheader+'</div>' if preheader else ''}
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 0">
  <tr><td align="center">
    <table width="580" cellpadding="0" cellspacing="0" style="max-width:580px;width:100%">
      <!-- Header -->
      <tr><td style="background:{_DARK};border-radius:10px 10px 0 0;padding:24px 32px;text-align:center">
        <span style="font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.5px">
          All<span style="color:{_RED}">Book</span>EU
        </span>
      </td></tr>
      <!-- Body -->
      <tr><td style="background:#fff;padding:32px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb">
        {content_html}
      </td></tr>
      <!-- Footer -->
      <tr><td style="background:#f9fafb;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 10px 10px;padding:20px 32px;text-align:center">
        <p style="margin:0 0 4px;font-size:12px;color:#9ca3af">AllBookEU · Kosovo & Albania's restaurant booking platform</p>
        <p style="margin:0;font-size:12px;color:#9ca3af">Questions? Reply to this email or visit <a href="{BASE_URL}" style="color:{_RED}">allbookeu.com</a></p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def _send(to, subject, html):
    if not resend.api_key:
        return
    try:
        resend.Emails.send({"from": SENDER, "to": [to], "subject": subject, "html": html})
    except Exception as e:
        print(f"[email] failed to send to {to}: {e}")


def send_booking_confirmation(booking, business):
    date_str = booking.booking_date.strftime('%A, %B %d, %Y')
    content = f"""
    <h2 style="margin:0 0 6px;font-size:22px;font-weight:800;color:#111">You're confirmed!</h2>
    <p style="margin:0 0 24px;color:#6b7280;font-size:15px">Your reservation at <strong>{business.name}</strong> is all set.</p>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:0;margin-bottom:24px">
      <tr><td style="padding:20px 24px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
              <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Restaurant</span><br>
              <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{business.name}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
              <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Date &amp; Time</span><br>
              <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{date_str} at {booking.booking_time}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
              <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Party size</span><br>
              <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{booking.party_size} {'guest' if booking.party_size == 1 else 'guests'}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 0">
              <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Name</span><br>
              <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{booking.customer_name}</span>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>

    {'<p style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:12px 16px;font-size:13px;color:#92400e;margin:0 0 20px"><strong>Note:</strong> ' + booking.notes + '</p>' if booking.notes else ''}

    <p style="margin:0 0 16px;font-size:14px;color:#6b7280">
      Need to cancel or change your reservation? Contact <strong>{business.name}</strong> directly
      {'at <a href="tel:'+business.phone+'" style="color:'+_RED+'">'+business.phone+'</a>' if business.phone else ''}.
    </p>

    <p style="margin:0;font-size:13px;color:#9ca3af">See you there!</p>
    """
    _send(
        booking.customer_email,
        f"Reservation confirmed — {business.name} · {booking.booking_time} {date_str}",
        _base(content, preheader=f"Your table at {business.name} is confirmed for {date_str} at {booking.booking_time}.")
    )


def send_new_booking_alert(booking, business, owner_email):
    date_str = booking.booking_date.strftime('%A, %B %d, %Y')
    content = f"""
    <h2 style="margin:0 0 6px;font-size:22px;font-weight:800;color:#111">New reservation incoming</h2>
    <p style="margin:0 0 24px;color:#6b7280;font-size:15px">
      <strong>{booking.customer_name}</strong> just booked a table at <strong>{business.name}</strong>.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;margin-bottom:24px">
      <tr><td style="padding:20px 24px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
            <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Date &amp; Time</span><br>
            <span style="font-size:16px;font-weight:800;color:{_RED};margin-top:2px;display:block">{date_str} · {booking.booking_time}</span>
          </td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
            <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Guest</span><br>
            <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{booking.customer_name}</span>
          </td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
            <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Party size</span><br>
            <span style="font-size:15px;font-weight:700;color:#111;margin-top:2px;display:block">{booking.party_size} {'guest' if booking.party_size == 1 else 'guests'}</span>
          </td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid #e5e7eb">
            <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Contact</span><br>
            <span style="font-size:14px;color:#374151;margin-top:2px;display:block">
              <a href="mailto:{booking.customer_email}" style="color:{_RED}">{booking.customer_email}</a>
              {' · <a href="tel:'+booking.customer_phone+'" style="color:'+_RED+'">'+booking.customer_phone+'</a>' if booking.customer_phone else ''}
            </span>
          </td></tr>
          {'<tr><td style="padding:8px 0"><span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">Note from guest</span><br><span style="font-size:14px;color:#374151;margin-top:2px;display:block">'+booking.notes+'</span></td></tr>' if booking.notes else ''}
        </table>
      </td></tr>
    </table>

    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td align="center">
        <a href="{BASE_URL}/biz/bookings" style="display:inline-block;background:{_RED};color:#fff;font-size:14px;font-weight:700;padding:12px 28px;border-radius:6px;text-decoration:none">
          View in Dashboard →
        </a>
      </td>
    </tr></table>
    """
    _send(
        owner_email,
        f"New reservation: {booking.customer_name} · {booking.booking_time} {booking.booking_date.strftime('%b %d')}",
        _base(content, preheader=f"{booking.customer_name} booked for {booking.party_size} on {date_str} at {booking.booking_time}.")
    )


def send_password_reset(to_email, name, reset_url, is_owner=False):
    account_type = 'restaurant dashboard' if is_owner else 'account'
    content = f"""
    <h2 style="margin:0 0 6px;font-size:22px;font-weight:800;color:#111">Reset your password</h2>
    <p style="margin:0 0 24px;color:#6b7280;font-size:15px">
      Hi {name.split()[0]}, we received a request to reset the password for your AllBookEU {account_type}.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px"><tr>
      <td align="center">
        <a href="{reset_url}" style="display:inline-block;background:{_RED};color:#fff;font-size:15px;font-weight:700;padding:14px 32px;border-radius:6px;text-decoration:none">
          Reset password
        </a>
      </td>
    </tr></table>

    <p style="margin:0 0 12px;font-size:13px;color:#9ca3af">
      This link expires in <strong>1 hour</strong>. If you didn't request a password reset, you can safely ignore this email.
    </p>
    <p style="margin:0;font-size:12px;color:#d1d5db;word-break:break-all">
      Or copy this link: {reset_url}
    </p>
    """
    _send(
        to_email,
        "Reset your AllBookEU password",
        _base(content, preheader="Click the link to set a new password. Expires in 1 hour.")
    )
