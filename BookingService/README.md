# Booking Service

FastAPI service for managing event ticket bookings: seat selection, reservations, payments (stub), and e-ticket generation.

## Features
- View seat maps and real-time availability (in-memory with reservation expiry)
- Create temporary reservations (holds)
- Create bookings and mark seats as booked
- Initiate payments (stub provider) and simulate provider callbacks
- Auto-pay booking flow for demos
- E-ticket generation upon successful confirmation
- Booking cancellation/refund demo behavior
- Basic analytics: tickets sold and revenue per event
- Role-based access control (attendee, organizer, admin) via simple Authorization header stub
- OpenAPI docs and JSON export

## Quick Start

1. Create environment file:
```
cp .env.example .env
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run service:
```
uvicorn src.api.main:app --reload --port 3002
```

Open Swagger UI: http://localhost:3002/docs

## Auth Stub and Roles

This service uses a simplified Authorization header for demo purposes. Use HTTP Bearer token with the following format:

```
Authorization: Bearer role:attendee;user_id:123
Authorization: Bearer role:organizer;user_id:org1
Authorization: Bearer role:admin;user_id:admin1
```

Multiple roles can be set by repeating `role:` segments:
```
Authorization: Bearer role:organizer;role:admin;user_id:42
```

Endpoints enforce roles:
- Attendee: can create reservations/bookings and view own bookings
- Organizer: can also access analytics and any booking (for their events in real systems; here allowed broadly)
- Admin: full access

Note: Replace this stub with real JWT/OAuth2 in production, ideally integrating with the UserService.

## Seat Map

GET `/events/{event_id}/seats` returns seat availability. The service auto-creates a small demo seat map per event on first access.

## Booking Flow

1. Optional Reservation (hold seats)
   - POST `/reservations` with event_id and seat_ids
   - Seats become `reserved` for `hold_minutes`

2. Create Booking
   - POST `/bookings` with event_id and seat_ids
   - Seats become `booked`
   - Booking is `pending` until payment succeeds

3. Payment
   - POST `/payments/initiate` to create a pending payment
   - POST `/payments/callback` with `status = success | failed` to finalize

4. E-ticket
   - On successful payment, an e-ticket is generated with a unique code and demo `pdf_url`

5. Cancel
   - POST `/bookings/{booking_id}/cancel`
   - If `pending`, seats are released and booking is `cancelled`
   - If `confirmed`, demo flow marks `refunded`, releases seats, and (if payment exists) status becomes `refunded`

## Analytics

- GET `/analytics/events/{event_id}/summary`
- Organizer/Admin only
- Returns tickets_sold and revenue for the event

## OpenAPI JSON

Generate OpenAPI spec:
```
python -m src.api.generate_openapi
```
Outputs to `interfaces/openapi.json`.

## Environment Variables

See `.env.example`. Do not hardcode secrets in code. Use environment variables.

## Notes

- This implementation uses an in-memory store for simplicity. Replace with a persistent database for production.
- Add proper concurrency controls and transactions in a real system to prevent double-booking.
