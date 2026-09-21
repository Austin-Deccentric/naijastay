# NaijaStay

A FastAPI-based hotel booking and property management API for guest room searches, room holds, and authentication.

## What the project currently includes

### API setup
- FastAPI app is created in [app/main.py](app/main.py)
- CORS is enabled
- SlowAPI rate limiting is enabled
- A request middleware adds:
  - a per-request ID
  - response timing header
  - request/response logging

### Authentication and user access
- Guest and receptionist access is enforced through role-based dependencies
- JWT authentication support is wired into the app flow
- Auth routes provide user registration and login behavior

### Room search
- Guests can search for rooms by query parameters:
  - `check_in`
  - `check_out`
  - `room_type`
- The endpoint is in [app/domains/rooms/router.py](app/domains/rooms/router.py)
- It validates that checkout is after check-in
- Results only include rooms that are genuinely free for the selected dates

### Room hold logic
- The booking domain includes a `Holds` model in [app/domains/bookings/models.py](app/domains/bookings/models.py)
- A hold lasts 10 minutes by default via `expires_at`
- A cleanup job removes expired and consumed holds in [app/domains/bookings/sweeps.py](app/domains/bookings/sweeps.py)
- Room availability checks ignore rooms with active holds

### Database lifecycle
- The application sets up async database sessions and a scheduler in [app/db/session.py](app/db/session.py)
- The scheduler runs the hold expiry sweeper automatically during app lifetime

## Recent work covered

- Added request logging middleware for cleaner API observability
- Switched room search to GET query parameters instead of a JSON body
- Added date validation to prevent invalid search ranges
- Added room hold expiry model and periodic cleanup logic
- Kept the implementation compact and focused on the actual booking flow

## Project structure

- [app/main.py](app/main.py) — app entry point and global middleware
- [app/core](app/core) — config, dependencies, rate limiting, permissions, error handling
- [app/db](app/db) — async DB session setup
- [app/domains/auth](app/domains/auth) — authentication logic
- [app/domains/rooms](app/domains/rooms) — room search and availability
- [app/domains/bookings](app/domains/bookings) — hold and booking models
- [app/domains/users](app/domains/users) — user models and routes

## Run locally

From the project root:

```bash
source .venv/Scripts/activate
uvicorn app.main:app --reload
```

## Notes

This project is still evolving around the guest room-hold flow. The core pieces for a 10-minute hold are in place, and the next natural step is to complete the actual guest action that creates and consumes a hold during payment.
