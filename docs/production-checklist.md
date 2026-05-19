# AllBookEU Production Checklist

Use this before launch and after every production deploy.

For daily platform operations, use `docs/management-guide.md`.

## Vercel

- `allbookeu.com` and `www.allbookeu.com` are attached to the production project.
- Production deployment points to the `main` branch.
- Vercel "Visit" opens `https://allbookeu.com`, not the preview or `vercel.app` URL.
- Environment variables are set in Production, Preview, and Development only where needed:
  - `NEON_DATABASE_URL`
  - `SECRET_KEY`
  - `ADMIN_SETUP_TOKEN`
  - `BASE_URL=https://allbookeu.com`
  - `RESEND_API_KEY`
  - `EMAIL_FROM=AllBookEU <noreply@allbookeu.com>`

## Neon

- Production uses the intended Neon branch and database.
- Connection string uses SSL and is saved only in Vercel env vars.
- Backup/restore is enabled or the Neon plan/history retention is acceptable for launch.
- Test data is either intentionally kept or removed before public launch.

## Email

- Resend sending domain is verified for `allbookeu.com`.
- SPF, DKIM, and DMARC DNS records are passing.
- Customer confirmation email links point to `https://allbookeu.com`.
- Restaurant alert email "View in Dashboard" opens `/biz/bookings`.

## Security

- Admin login is only at `/admin/login`.
- Setup endpoints require `ADMIN_SETUP_TOKEN`.
- Forms reject missing CSRF tokens.
- Login, signup, forgot password, and booking POSTs return `429` after repeated attempts.
- Replace in-memory rate limits with Upstash Redis, Cloudflare Turnstile, or similar before heavy traffic.

## Smoke Tests

- Home page loads.
- Search by city/cuisine works.
- Restaurant page shows available times by party size.
- A guest can create a valid future booking.
- Past-date booking is rejected.
- Restaurant owner can log in and view `/biz/dashboard`.
- Owner can open `/biz/bookings`, mark Done, cancel, and restore a booking.
- Owner can pause and resume reservations.
- Privacy, terms, 404, 500, and 429 pages are branded.

## Mobile Launch Readiness

- Customer booking flow works on iPhone-sized screens.
- Owner dashboard, reservations, tables, profile, and schedule are usable on phone.
- No text overlaps in the top nav, dashboard cards, tables, or modal forms.
- Android Chrome and iPhone Safari have been checked manually.

## App Store Prep

- Privacy policy is final and public at `/privacy`.
- Terms are final and public at `/terms`.
- App name, icon, screenshots, support email, and privacy labels are ready.
- Decide whether v1 is a wrapped web app/PWA shell or a React Native/Expo app.
