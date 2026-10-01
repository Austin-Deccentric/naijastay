# Deploying NaijaStay to Render (free tier)

## One-click path

1. Push this repo to GitHub (it already has `origin` set).
2. In the [Render Dashboard](https://dashboard.render.com), **New → Blueprint**, and point it at this repo. Render reads `render.yaml` and provisions:
   - `naijastay-api` — web service, Docker, free plan
   - `naijastay-db` — managed Postgres, free plan
   - `naijastay-redis` — Key Value (Redis-compatible), free plan, internal only
3. No manual env vars needed. Everything is wired in the Blueprint:
   - `DATABASE_URL` and `REDIS_URL` come from the provisioned services
   - `JWT_SECRET_KEY` and `WEBHOOK_SECRET` are auto-generated per deploy
4. Open the service URL → `/docs` for the interactive API.

## What the Blueprint sets (and why)

| Var | Value | Notes |
|---|---|---|
| `DATABASE_URL` | from `naijastay-db` | Render-managed Postgres |
| `REDIS_URL` | from `naijastay-redis` | Key Value free tier (25 MB, no persistence). Fine for holds + cache demo |
| `JWT_SECRET_KEY` | `generateValue` | Fresh 256-bit secret per deploy. Never reuse the local `.env` value |
| `JWT_ALGORITHM` | `HS256` | Matches local dev |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Matches local dev |
| `RATE_LIMIT_GLOBAL` | `30/minute` | Looser than local (`10/minute`) so demo traffic doesn't trip the limiter |
| `RATE_LIMIT_LOGIN` | `10/minute` | Looser than local (`5/minute`) |
| `RATE_LIMIT_REGISTER` | `20/hour` | Looser than local (`10/hour`) |
| `WEBHOOK_SECRET` | `generateValue` | Satisfies the 8-char minimum; rotate if webhooks go live |
| `SEED_ON_BOOT` | `"true"` | Demo starts with rooms, guests, and staff loaded |

## ⚠️ Seeding is destructive

`SEED_ON_BOOT=true` runs `scripts/seed.py --reset --yes` on every boot,
which issues `TRUNCATE ... CASCADE`. That is the point for a throwaway demo,
and it is data loss anywhere else. The entrypoint keeps seeding behind the
env flag (default `false`), so deleting that one line from `render.yaml`
restores safe behavior.

## CORS is unset on purpose

`CORS_ALLOWED_ORIGINS` is not in the Blueprint, so the app defaults to `None`
(no cross-origin access). `/docs` is same-origin and works fine. If a browser
frontend ever needs to call this API cross-origin, set it to the exact frontend
origin — never `*` while auth cookies or JWTs are in play.

## Free-tier caveats

- The web service sleeps after inactivity; first request takes ~30–60s to wake.
- Key Value free has no persistence: holds and cache reset if Redis restarts.
  Postgres data persists normally.
- Postgres free tier has usage limits; a demo won't hit them.
