# AllBookEU Management Guide

Keep this simple: admin manages the platform, restaurant owners manage their own restaurant, guests book from the public site.

## Important URLs

- Public site: `https://allbookeu.com`
- Restaurant owner login: `https://allbookeu.com/auth/login?tab=owner`
- Customer login: `https://allbookeu.com/auth/login`
- Admin login: `https://allbookeu.com/admin/login`
- Owner dashboard after login: `/biz/dashboard`
- Owner reservations: `/biz/bookings`
- Admin dashboard after login: `/admin/`

## Admin Workflow

Use admin for platform-level work:

- Approve or reject new restaurant owner signups.
- Add/edit/remove restaurants.
- Feature restaurants on the home page.
- Review all bookings across the platform.
- Delete inappropriate reviews.
- Suspend an owner account if needed.

Recommended routine:

1. Open `/admin/login`.
2. Check pending restaurant approvals.
3. Review today's bookings.
4. Check restaurants for missing photos, phone numbers, or cities.
5. Feature only polished listings.

## Restaurant Owner Workflow

Owners should manage the day-to-day restaurant operations:

- View today's reservations from `/biz/dashboard`.
- Manage all reservations from `/biz/bookings`.
- Mark reservations as done, cancel them, or restore cancelled ones.
- Pause/resume reservations from the dark sidebar status box.
- Add tables from `/biz/tables`.
- Configure bookable shifts from `/biz/shifts`.
- Update restaurant info, photos, hours, and password from `/biz/profile`.

Recommended routine:

1. Log in before service.
2. Check today's reservations.
3. Confirm the table setup is accurate.
4. Pause reservations if the restaurant is full, closed, or unavailable.
5. Mark completed/cancelled reservations during or after service.

## Launch Smoke Test

Run this after deploys and before telling people to use the site:

- Home page loads.
- Search works for Prishtina/Tirana.
- A restaurant page opens and shows booking times.
- Guest booking creates a reservation.
- Customer confirmation email sends.
- Owner alert email sends.
- Owner alert button opens `/biz/bookings` on `allbookeu.com`.
- Owner can mark the booking done and cancel/restore it.
- Admin can log in and see the booking.

## App Store Prep

Before building the iPhone app:

- Confirm the mobile web flow feels good on a real iPhone.
- Keep `/privacy` and `/terms` live.
- Decide app v1 approach:
  - Fastest: native wrapper/PWA-style app around `allbookeu.com`.
  - Better long term: Expo/React Native app with native screens.
- Prepare app name, icon, screenshots, support email, and privacy labels.

## Rules Of Thumb

- Keep the public site simple for guests: search, pick time, book.
- Keep owner tools focused on daily service: reservations, tables, shifts, pause/resume.
- Keep admin tools limited to platform control and quality.
- Do not edit production database manually unless you have a backup path.
