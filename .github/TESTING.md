# Testing Guide

## Automated Tests (GitHub Actions)

Tests run automatically on every push to `main` and every pull request.

**Workflow:** `.github/workflows/test.yml`

### What's Tested

1. **Backend Loader Tests** (`backend/tests/test_loader_*.py`)
   - Requires PostgreSQL with PostGIS (spun up in CI)
   - Tests data loading, upserts, import boundaries
   - ~10 tests, ~30 seconds

2. **Pure Function Tests** (`backend/src/transitcov/tests/`)
   - No database required
   - Tests accessibility formula, GTFS modes, parameters
   - 21 tests, deterministic, order-independent
   - ~1 second

3. **Import Boundaries**
   - Verifies `transitcov/` has no imports from `app/`, `sqlalchemy`, `psycopg`
   - Enforces separation of concerns

4. **Type Checking** (mypy)
   - Runs on app loaders and transitcov library
   - Non-blocking (warnings only)

5. **Linting** (flake8, isort)
   - Code style checks
   - Non-blocking (informational only)

6. **Coverage Report**
   - Uploaded to Codecov
   - Tracks test coverage over time

### CI Status Badge

Add to `README.md`:

```markdown
[![Tests](https://github.com/minhle35/transit-coverage-platform/actions/workflows/test.yml/badge.svg)](https://github.com/minhle35/transit-coverage-platform/actions/workflows/test.yml)
```

---

## Local Testing

### Prerequisites

1. **Python 3.12+**
2. **uv** package manager
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. **PostgreSQL 16 + PostGIS**
   ```bash
   # macOS
   brew install postgresql postgis
   
   # or via Docker
   docker run -d \
     -e POSTGRES_USER=transit_user \
     -e POSTGRES_PASSWORD=postgres \
     -e POSTGRES_DB=transit \
     -p 5432:5432 \
     postgis/postgis:16-3.4
   ```

### Setup

```bash
cd backend

# Install dependencies
uv sync

# Install transitcov library in editable mode
uv pip install -e src/transitcov

# Run Alembic migrations
uv run alembic upgrade head
```

### Run Tests

**All tests:**
```bash
cd backend
uv run pytest tests/ src/transitcov/tests/ -v
```

**Loader tests only** (requires database):
```bash
cd backend
uv run pytest tests/test_loader_*.py -v
```

**Pure function tests** (no database required):
```bash
cd backend/src/transitcov
uv run pytest tests/ -v
```

**Specific test:**
```bash
cd backend
uv run pytest tests/test_loader_gtfs.py::test_transform_creates_point_geometries -v
```

**With coverage:**
```bash
cd backend
uv run pytest tests/ --cov=src/app --cov-report=html
# Open htmlcov/index.html in browser
```

### Check Code Quality

**Type check:**
```bash
cd backend
uv run mypy src/app/loaders/ src/transitcov/src/transitcov/ --ignore-missing-imports
```

**Lint:**
```bash
cd backend
uv run flake8 src/ --max-line-length=100
```

**Import sorting:**
```bash
cd backend
uv run isort --check-only src/
# Or fix automatically:
uv run isort src/
```

**Format:**
```bash
cd backend
uv run black src/
```

---

## Test Structure

### Backend Loader Tests

Located: `backend/tests/test_loader_*.py`

- `test_loader_geo.py` — SA1 boundary loading, CRS conversion
- `test_loader_census.py` — Population parsing, pseudo-SA1 handling
- `test_loader_gtfs.py` — Stop deduplication, mode resolution, geometry
- `test_loader_feed_version.py` — Feed version metadata, upsert idempotency
- `conftest.py` — Provides `session` fixture for database tests

**Run with database:**
```bash
cd backend
uv run pytest tests/test_loader_*.py -v
```

### Pure Function Tests

Located: `backend/src/transitcov/tests/`

- `test_accessibility.py` — Scoring formula, decay rates, worked example
- `test_modes.py` — GTFS route_type mapping

**Run without database:**
```bash
cd backend/src/transitcov
uv run pytest tests/ -v
```

All tests are deterministic and order-independent.

---

## Expected Test Results

**Local run:**
```
backend/tests/test_loader_*.py         ~10 tests, ~30s
backend/src/transitcov/tests/          21 tests, ~1s
────────────────────────────────────────────────
Total                                  ~31 tests, ~31s
```

**GitHub Actions run:**
```
Jobs (parallel):
  - test (31 tests, ~40s)
  - lint (~5s)
  - type-check (~10s)
────────────────────────────
Total time: ~50s
```

---

## Troubleshooting

### Database Connection Error

**Error:** `psycopg2.OperationalError: could not connect to server`

**Fix:** Ensure PostgreSQL is running:
```bash
# Check if running
psql -h localhost -U transit_user -d transit -c "SELECT 1"

# Start if stopped (macOS)
brew services start postgresql

# Or use Docker
docker run -d -e POSTGRES_USER=transit_user -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=transit -p 5432:5432 postgis/postgis:16-3.4
```

### Alembic Migration Error

**Error:** `sqlalchemy.exc.ProgrammingError: (psycopg2.ProgrammingError)`

**Fix:** Ensure migrations have run:
```bash
cd backend
uv run alembic upgrade head
```

### Import Error: No module named 'transitcov'

**Error:** `ModuleNotFoundError: No module named 'transitcov'`

**Fix:** Install the library:
```bash
cd backend
uv pip install -e src/transitcov
```

### Tests Pass Locally but Fail in CI

**Common causes:**
1. Different Python version (CI uses 3.12.x, check local)
2. Environment variables not set (check `.env` vs. CI secrets)
3. Database state (migrations not run in CI; check `.github/workflows/test.yml`)

**Debug:** Run same commands as CI locally:
```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/test_loader_*.py -v
```

---

## Adding New Tests

1. **Loader test** (requires database):
   ```python
   # backend/tests/test_loader_new.py
   from app.loaders import new_loader
   from app.loaders.db import get_session
   
   def test_new_loader_loads_data():
       with get_session() as session:
           result = new_loader.load(data, session)
           assert result > 0
   ```

2. **Pure function test** (no database):
   ```python
   # backend/src/transitcov/tests/test_new_module.py
   from transitcov.new_module import pure_function
   
   def test_pure_function():
       result = pure_function(input_data)
       assert result == expected
   ```

3. **Commit & push:**
   ```bash
   git add tests/
   git commit -m "test: add tests for new_module"
   git push origin your-branch
   # CI runs automatically on PR
   ```

---

## CI Configuration

**Main workflow:** `.github/workflows/test.yml`

- **Triggers:** Push to `main`, PR against `main`
- **Jobs:** test, lint, type-check (parallel)
- **Services:** PostgreSQL 16 + PostGIS 3.4
- **Coverage:** Uploaded to Codecov

**Modify CI:**
1. Edit `.github/workflows/test.yml`
2. Push to a branch (CI runs)
3. Review results in GitHub Actions tab
4. Merge when green

---

## Coverage Goals

| Module | Target | Current |
|--------|--------|---------|
| `app/loaders/` | 80% | TBD |
| `app/models/` | 60% | TBD |
| `transitcov/scoring/` | 100% | 100% |
| `transitcov/gtfs/` | 100% | 100% |

Run locally to check:
```bash
cd backend
uv run pytest tests/ --cov=src/app --cov-report=term-missing
```
