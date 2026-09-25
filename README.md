# 🇳🇬 NaijaStay

### Hotel Booking & Management API

NaijaStay is a backend API for managing hotel rooms, guests, staff, bookings, availability, and day-to-day hotel operations.

The project was built with **FastAPI and SQLModel**, with **PostgreSQL** as the primary database and **Redis** for caching and temporary booking holds. It is designed around a clear role-based workflow so that guests can make bookings while hotel staff can manage reservations and room operations according to their responsibilities.

The goal is not simply to create another CRUD API. NaijaStay models some of the practical problems that exist in a real hotel environment — including room availability, temporary booking holds, booking conflicts, staff permissions, check-in/check-out workflows, housekeeping states, caching, rate limiting, and database migrations.

---

## 📌 Project Overview

A hotel booking system has to do more than store a reservation.

For example, when a guest searches for a room, the system needs to determine whether that room is genuinely available for the requested dates. If a guest temporarily holds a room while completing a booking, another guest should not be able to take the same room during that period.

At the same time, hotel employees should not all have the same level of access.

NaijaStay therefore separates responsibilities using role-based access control:

* **Guest** — registers, signs in, searches for rooms, places temporary holds, and makes bookings.
* **Receptionist** — manages bookings and performs front-desk operations such as booking, check-in, and check-out.
* **Housekeeper** — manages room cleaning status after guests check out.
* **Manager** — manages staff access, room pricing, and operational reporting.

The backend exposes these workflows through a RESTful API.

---

## ✨ Core Features

### Authentication & Authorization

* User registration and authentication
* JWT-based authentication
* Password hashing with bcrypt
* Role-based access control
* Protected API endpoints
* Separate permissions for guests, receptionists, housekeepers, and managers
* Manager-controlled staff account management
* Ability to disable staff accounts

### Room Management

* Room types with configurable rates and capacities
* Individual hotel rooms linked to room types
* Room availability checks
* Search rooms by:

  * Check-in date
  * Check-out date
  * Room type
* Server-side availability validation
* Manager-only room-type price updates

### Booking Management

* Guest room holds
* Temporary booking protection
* Booking creation for guests and receptionists
* Booking status tracking
* Server-side price calculation
* Date validation
* Prevention of overlapping room bookings
* Booking workflow from processing to confirmation/cancellation

### Check-in & Check-out

Receptionists can:

* Check guests into their booked rooms
* Validate booking and check-in dates
* Prevent invalid duplicate check-ins
* Check guests out
* Mark rooms as requiring cleaning after checkout

Housekeepers can then:

* View/manage rooms requiring cleaning
* Mark cleaned rooms as available for use again

### Caching

Redis is used to improve performance for data that is frequently requested but does not change constantly.

The caching strategy focuses on appropriate read-heavy endpoints rather than caching booking operations indiscriminately.

Relevant cached data can be invalidated when the underlying room or pricing information changes.

### Rate Limiting

The API includes rate limiting to help protect endpoints from excessive requests and reduce abuse, particularly around sensitive operations.

### Logging

A middleware-based logging layer records useful request information to make the application easier to monitor and debug without scattering logging code throughout individual endpoints.

### Database Migrations

Database schema changes are managed through **Alembic**.

The application does not rely on `SQLModel.metadata.create_all()` for normal schema management.

This makes database changes explicit, trackable, and reproducible across environments.

### Health Check

The application exposes a health endpoint that can be used by Docker and deployment infrastructure to determine whether the API is running correctly.

### Docker Support

The project includes a `compose.yaml` configuration for running:

* NaijaStay API
* PostgreSQL
* Redis

PostgreSQL and Redis include health checks, while the API waits for those services to become healthy before starting.

---

# 🏗️ Architecture

NaijaStay follows a domain-oriented backend structure.

```text
NaijaStay
│
├── app/
│   ├── core/
│   │   ├── authentication
│   │   ├── authorization
│   │   ├── configuration
│   │   └── security
│   │
│   ├── db/
│   │   ├── database/session management
│   │   └── database dependencies
│   │
│   ├── domains/
│   │   ├── users/
│   │   ├── rooms/
│   │   └── bookings/
│   │
│   ├── middleware/
│   │   └── request logging
│   │
│   └── main.py
│
├── migrations/
│   └── Alembic migrations
│
├── .env.example
├── .gitignore
├── alembic.ini
├── compose.yaml
├── makefile
├── pyproject.toml
└── uv.lock
```

The exact implementation may evolve as the project grows, but the main principle is to keep authentication, database access, business domains, and application configuration separated.

---

# 🔐 Role-Based Access

NaijaStay uses four primary roles.

| Role           | Main Responsibility                                 |
| -------------- | --------------------------------------------------- |
| `guest`        | Account access, room search, holds and bookings     |
| `receptionist` | Bookings, guest check-in and check-out              |
| `housekeeper`  | Room cleaning workflow                              |
| `manager`      | Staff management, pricing and operational oversight |

Authorization is handled through reusable role dependencies rather than duplicating permission checks throughout every endpoint.

This keeps access control consistent and makes the API easier to maintain.

---

# 🛏️ Room Availability

Room availability is one of the most important parts of NaijaStay.

A room should not simply be considered available because its `is_available` flag is set to `true`.

When searching for rooms, the system considers existing reservations and temporary holds for the requested date range.

Conceptually:

```text
Guest searches
      │
      ▼
Check requested dates
      │
      ▼
Find rooms matching room type
      │
      ▼
Check existing bookings
      │
      ▼
Check active temporary holds
      │
      ▼
Remove unavailable rooms
      │
      ▼
Return genuinely available rooms
```

This prevents the API from presenting a room as available when another booking already occupies the requested dates.

---

# ⏳ Temporary Room Holds

NaijaStay uses temporary holds to protect a room during the booking process.

The basic workflow is:

```text
Guest selects room
       │
       ▼
Temporary hold created
       │
       ▼
Room protected for a limited period
       │
       ├── Booking completed → Hold consumed
       │
       └── Booking not completed → Hold expires
```

Redis can be used alongside the application for fast temporary data and caching, while the database remains the source of truth for persistent booking information.

---

# 📅 Booking Lifecycle

Bookings use explicit statuses to represent their lifecycle.

```text
PROCESSING
     │
     ▼
 CONFIRMED
     │
     ├── Check-in
     │
     ▼
 Guest stays
     │
     ▼
 Check-out
     │
     ▼
 Room requires cleaning
```

Bookings can also be cancelled where the relevant workflow allows it.

The booking price is calculated by the backend rather than trusting a price supplied by the client.

For a normal room booking:

```text
Total = Room nightly rate × Number of nights
```

This prevents clients from manipulating the final booking amount.

---

# 🧹 Room Operations

NaijaStay separates booking status from room-cleaning operations.

After checkout:

```text
Guest checks out
       │
       ▼
Room becomes dirty
       │
       ▼
Housekeeper cleans room
       │
       ▼
Room marked clean
```

This mirrors an actual hotel workflow where a room cannot immediately be treated as ready simply because the previous booking has ended.

---

# 💾 Database

NaijaStay uses:

* **PostgreSQL** for persistent data
* **SQLModel** for database models
* **Alembic** for schema migrations
* **Psycopg** for PostgreSQL connectivity

The database contains the main entities required to support users, room types, rooms, bookings, holds, and room-night availability tracking.

The project uses migrations instead of relying on automatic table creation.

---

# ⚡ Redis

Redis is included as part of the application infrastructure.

It is useful for:

* API response caching
* Temporary room holds
* Frequently requested room information
* Reducing repeated database queries
* Supporting faster read operations

The Docker configuration runs Redis with AOF persistence enabled.

---

# 🛡️ Security

Security is treated as part of the application architecture rather than something added after the main functionality.

NaijaStay includes:

* JWT authentication
* Password hashing with bcrypt
* Role-based authorization
* Environment-based secret configuration
* Request rate limiting
* Server-side validation
* Server-side booking price calculation
* Protected staff operations
* Database-backed account status
* Temporary booking holds to reduce booking conflicts

Sensitive configuration such as database credentials and JWT secrets should be provided through environment variables and should never be committed to the repository.

---

# 🚦 Rate Limiting

The API uses `SlowAPI` for request rate limiting.

Rate limiting helps prevent excessive requests to the application and provides an additional layer of protection around sensitive endpoints.

The exact limits are configured through the application's environment/configuration rather than being hard-coded throughout individual routers.

---

# 📝 Request Logging

NaijaStay includes middleware for request logging.

The middleware provides a centralized place to capture information such as:

* HTTP method
* Request path
* Response status
* Request processing time

Centralizing this functionality keeps the individual routers focused on business logic.

---

# 🔄 Database Migrations

Alembic is used to manage database schema changes.

### Apply existing migrations

```bash
uv run alembic upgrade head
```

### Create a new migration

```bash
uv run alembic revision --autogenerate -m "describe your change"
```

### Roll back one migration

```bash
uv run alembic downgrade -1
```

### Check the current migration

```bash
uv run alembic current
```

The repository also provides Makefile shortcuts for these operations.

---

# 🧰 Technology Stack

| Technology         | Purpose                                      |
| ------------------ | -------------------------------------------- |
| **Python 3.14+**   | Programming language                         |
| **FastAPI**        | REST API framework                           |
| **SQLModel**       | ORM/model layer                              |
| **PostgreSQL**     | Primary relational database                  |
| **Psycopg**        | PostgreSQL driver                            |
| **Alembic**        | Database migrations                          |
| **PyJWT**          | JWT authentication                           |
| **bcrypt**         | Password hashing                             |
| **Redis**          | Caching and temporary data                   |
| **SlowAPI**        | Rate limiting                                |
| **SSE-Starlette**  | Server-Sent Events support                   |
| **APScheduler**    | Scheduled/background jobs                    |
| **Docker Compose** | Local service orchestration                  |
| **uv**             | Python dependency and environment management |

These dependencies are defined in the project's `pyproject.toml`.

---

# 📋 API Documentation

Once the application is running, FastAPI automatically provides interactive API documentation.

### Swagger UI

```text
http://localhost:8000/docs
```

### ReDoc

```text
http://localhost:8000/redoc
```

Swagger is particularly useful during development because it allows endpoints to be tested directly from the browser.

---

# 🚀 Getting Started

## Prerequisites

Make sure you have the following installed:

* Python 3.14+
* [uv](https://docs.astral.sh/uv/)
* PostgreSQL
* Redis
* Docker Desktop (recommended for running the complete stack)
* Git

---

## 1. Clone the repository

```bash
git clone https://github.com/Austin-Deccentric/naijastay.git
cd naijastay
```

---

## 2. Install dependencies

Using `uv`:

```bash
uv sync
```

The repository includes a `uv.lock` file so dependency versions can be reproduced consistently.

---

## 3. Configure environment variables

Create your local environment file:

```bash
cp .env.example .env
```

Then update `.env` with your local PostgreSQL, Redis, JWT, rate-limit, and other application configuration values.

> Never commit your real `.env` file or production secrets to Git.

---

# 🐳 Running with Docker

The repository includes a Docker Compose configuration containing three main services:

```text
NaijaStay API
     │
     ├── PostgreSQL
     │
     └── Redis
```

Start the stack with:

```bash
docker compose up --build
```

The API runs on:

```text
http://localhost:8000
```

The Compose configuration exposes:

* API → `8000`
* PostgreSQL → `5432`
* Redis → `6379`

PostgreSQL and Redis have health checks configured so the API waits for their services to become ready.

---

# 💻 Running Locally Without Docker

After installing the dependencies and configuring your environment:

### Start the development server

```bash
uv run fastapi dev app.main:app
```

Or:

```bash
make dev
```

### Run the application

```bash
uv run fastapi run app.main:app
```

Or:

```bash
make run
```

These commands are already defined in the repository's Makefile.

---

# 🛠️ Makefile Commands

The project includes shortcuts for common development tasks.

```bash
make install
```

Install/synchronize dependencies.

```bash
make dev
```

Start the development server with reload.

```bash
make run
```

Run the application normally.

```bash
make migrate
```

Apply pending Alembic migrations.

```bash
make makemigration m="describe your change"
```

Generate a new migration.

```bash
make downgrade
```

Roll back one migration.

```bash
make current
```

Show the current migration revision.

The Makefile is intended to reduce repetitive commands during development.

---

# 🔁 Typical Booking Flow

A typical guest booking journey looks like this:

```text
1. Register / Sign in
          │
          ▼
2. Search rooms
   by dates + room type
          │
          ▼
3. Select an available room
          │
          ▼
4. Place temporary hold
          │
          ▼
5. Create booking
          │
          ▼
6. Server calculates total
          │
          ▼
7. Booking enters processing
          │
          ▼
8. Booking becomes confirmed
          │
          ▼
9. Receptionist checks guest in
          │
          ▼
10. Guest stays
          │
          ▼
11. Receptionist checks guest out
          │
          ▼
12. Room becomes dirty
          │
          ▼
13. Housekeeper cleans room
          │
          ▼
14. Room becomes clean/ready
```

This separation keeps the booking lifecycle and physical room lifecycle understandable and independent.

---

# 👥 Staff Workflow

### Manager

```text
Manager
   │
   ├── Manage staff accounts
   ├── Disable staff accounts
   ├── Manage room pricing
   └── View operational information
```

### Receptionist

```text
Receptionist
   │
   ├── Search/book rooms
   ├── Create bookings
   ├── Check guests in
   └── Check guests out
```

### Housekeeper

```text
Housekeeper
   │
   └── Mark cleaned rooms as ready
```

This ensures each staff member only performs operations appropriate to their role.

---

# 🧪 Development Philosophy

A few principles guide the project:

### Keep business logic out of routers

Routers should primarily handle HTTP concerns.

Business rules belong in service/domain logic where they can be reused and tested independently.

### Validate on the server

The client is never treated as a trusted source for important business values such as booking prices or room availability.

### Use the database as the source of truth

Redis improves performance, but persistent booking information remains in PostgreSQL.

### Prefer explicit permissions

Access should be granted through role dependencies instead of relying on assumptions inside endpoint functions.

### Keep the codebase maintainable

The project favors small domain modules, reusable dependencies, explicit schemas, migrations, and centralized infrastructure concerns.

---

# 📂 Important Project Files

| File / Directory | Purpose                           |
| ---------------- | --------------------------------- |
| `app/`           | Main FastAPI application          |
| `app/main.py`    | Application entry point           |
| `migrations/`    | Alembic database migrations       |
| `.env.example`   | Environment variable template     |
| `alembic.ini`    | Alembic configuration             |
| `compose.yaml`   | Docker Compose infrastructure     |
| `makefile`       | Common development commands       |
| `pyproject.toml` | Project metadata and dependencies |
| `uv.lock`        | Locked Python dependency versions |
| `.gitignore`     | Files excluded from Git           |

The current repository contains these core project files alongside the application and migration directories.

---

# 🧭 Project Status

NaijaStay is an actively developed backend/capstone project.

The current repository contains the core infrastructure and backend functionality required for hotel account management, room availability, booking workflows, staff operations, database migrations, caching, rate limiting, and supporting application infrastructure.

Some infrastructure components are already present specifically to support continued development, including Redis, scheduled jobs, and Server-Sent Events support.

---

# 🔮 Potential Future Improvements

Possible future iterations include:

* Payment gateway integration
* Booking confirmation notifications
* Email/SMS notifications
* More advanced occupancy analytics
* Hotel-wide reporting dashboards
* Automated expired-hold cleanup
* More extensive automated tests
* CI/CD pipelines
* Production observability
* API versioning
* Frontend client
* More advanced reservation modification/cancellation workflows

These are possible extensions rather than requirements of the current implementation.

---

# 🤝 Contributing

Contributions and improvements are welcome.

A typical workflow is:

```bash
git checkout -b feature/your-feature
```

Make your changes, run the application and tests, then commit:

```bash
git add .
git commit -m "describe your change"
```

Push the branch:

```bash
git push origin feature/your-feature
```

Then open a pull request.

---

# 📄 License

This project currently does not specify a license in the repository.

If the project is intended for public reuse, an appropriate open-source license can be added later.

---

# 👨🏽‍💻 About NaijaStay

NaijaStay is a practical backend engineering project focused on building a hotel booking system around real-world backend concerns rather than only basic CRUD operations.

The project demonstrates the use of:

* REST API design
* Authentication
* Authorization
* Relational database modelling
* Transactional booking workflows
* Availability checking
* Temporary holds
* Caching
* Rate limiting
* Middleware
* Database migrations
* Docker-based infrastructure
* Background scheduling
* Server-Sent Events

The intention is to build the system in a way that is understandable, maintainable, and close to the kinds of backend patterns used in real applications.

---

## 🔗 Repository

**GitHub:**
https://github.com/Austin-Deccentric/naijastay

**API Documentation (when running locally):**

```text
http://localhost:8000/docs
```

---

### Built with Python, FastAPI, PostgreSQL, Redis and a lot of backend engineering. 🇳🇬
