# filamind-iot-proxy backend

FastAPI service. See [`../README.md`](../README.md) and
[`../ROADMAP.md`](../ROADMAP.md) for the project context.

## Local dev

```bash
# 1. Install in editable mode + dev extras
cd backend
pip install -e ".[dev]"

# 2. Bring up Postgres + Redis (from repo root)
cd ..
cp .env.example .env  # fill in DB_PASSWORD
docker compose up -d proxy-db proxy-redis

# 3. Apply migrations
cd backend
alembic upgrade head

# 4. Run dev server
uvicorn api.app:app --reload --port 9100

# 5. Run tests (uses sqlite + fakeredis, no docker needed)
pytest
```

## Layout

```
backend/
├── pyproject.toml         # dependencies + tool config
├── alembic.ini            # migrations config
├── alembic/               # versioned migrations
│   └── versions/
├── api/                   # the FastAPI app
│   ├── __init__.py
│   ├── app.py             # FastAPI() + middleware + lifespan
│   ├── config.py          # pydantic-settings env reader
│   ├── db.py              # async SQLAlchemy engine
│   ├── redis_store.py     # Redis client wrapper
│   ├── models.py          # SQLAlchemy ORM tables
│   ├── schemas.py         # pydantic request/response
│   ├── routes/
│   │   ├── health.py
│   │   ├── pairing.py
│   │   └── admin.py
│   └── services/
│       └── pairing.py     # business logic
└── tests/
    ├── conftest.py        # in-memory db + fake redis
    └── test_pairing.py
```
