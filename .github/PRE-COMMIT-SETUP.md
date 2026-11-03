# Pre-commit Hooks Setup

Pre-commit hooks run checks **locally before you push** to prevent broken code from reaching GitHub Actions.

## One-Time Setup

### 1. Install pre-commit

```bash
pip install pre-commit
```

Or with Homebrew (macOS):
```bash
brew install pre-commit
```

### 2. Install the hooks

```bash
cd /path/to/transit-coverage-platform
pre-commit install
```

This creates `.git/hooks/pre-commit` that runs on every `git commit`.

### 3. (Optional) Run on all files

```bash
pre-commit run --all-files
```

This checks all files in the repo (useful after installing for the first time).

---

## What Gets Checked

| Check | Tool | What It Does |
|-------|------|-------------|
| **Trailing whitespace** | pre-commit-hooks | Removes trailing spaces |
| **End-of-file fixer** | pre-commit-hooks | Ensures files end with newline |
| **YAML validation** | pre-commit-hooks | Checks `.yml` syntax |
| **Large files** | pre-commit-hooks | Rejects files > 1MB |
| **Merge conflicts** | pre-commit-hooks | Catches unresolved conflicts |
| **Private keys** | pre-commit-hooks | Detects secrets (API keys, etc.) |
| **Code formatting** | black | Formats Python code consistently |
| **Import sorting** | isort | Sorts and groups imports |
| **Linting** | flake8 | Checks code style, catches common errors |
| **Type checking** | mypy | Validates type hints |
| **Loader tests** | pytest | Runs `backend/tests/test_loader_*.py` |
| **Library tests** | pytest | Runs `backend/src/transitcov/tests/` |

---

## Workflow

### Normal commit (with pre-commit)

```bash
git add .
git commit -m "feat: add new feature"

# Pre-commit hooks run automatically:
# - Check code formatting (black, isort)
# - Lint (flake8)
# - Type check (mypy)
# - Run tests (pytest)
#
# If any check fails, commit is blocked.
# Fix the issue, then commit again.
```

### Bypass hooks (not recommended)

```bash
git commit --no-verify -m "skip checks"
```

⚠️ Only use if you're sure. CI will catch the issue anyway.

---

## Common Issues & Fixes

### Issue: "pre-commit: command not found"

**Fix:** Install pre-commit:
```bash
pip install pre-commit
pre-commit install
```

### Issue: Hooks run but fail on imports

**Error:** `ModuleNotFoundError: No module named 'app'`

**Fix:** Install dependencies:
```bash
cd backend
uv sync
uv pip install -e src/transitcov
```

### Issue: Tests fail because database isn't running

**Error:** `psycopg2.OperationalError: could not connect to server`

**Fix:** Start PostgreSQL:
```bash
# macOS
brew services start postgresql

# Or use Docker
docker run -d \
  -e POSTGRES_USER=transit_user \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=transit \
  -p 5432:5432 \
  postgis/postgis:16-3.4
```

### Issue: Black and isort disagree on formatting

**Fix:** They should be compatible by default. If issues persist:
```bash
cd backend
uv run black src/
uv run isort src/
```

### Issue: Hook takes too long

Pre-commit runs all checks on every commit. To speed up:

**Option 1:** Skip certain hooks for now
```bash
# Edit .pre-commit-config.yaml and comment out slow hooks
```

**Option 2:** Use `--skip` flag
```bash
git commit --skip=mypy -m "commit message"
```

**Option 3:** Run tests manually before committing
```bash
# First time setup only
pre-commit install --install-hooks
# Then configure to skip pytest in pre-commit config
```

---

## Manual Checks

You can run checks manually without committing:

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files

# Run on staged files only (default)
pre-commit run
```

---

## Update Hooks

Keep hook versions up to date:

```bash
pre-commit autoupdate
```

This updates `.pre-commit-config.yaml` with latest versions.

---

## Disable Pre-commit

If you need to disable hooks temporarily:

```bash
# Uninstall hooks
pre-commit uninstall

# Re-install later
pre-commit install
```

---

## Configuration

Edit `.pre-commit-config.yaml` to customize:

```yaml
- repo: https://github.com/psf/black
  rev: 24.10.0
  hooks:
    - id: black
      args: ['--line-length=100']  # Adjust line length
      exclude: ^backend/migrations/  # Skip certain files
```

Common customizations:
- `args`: Pass command-line arguments to the tool
- `exclude`: Skip files matching this pattern
- `stages`: Run at [commit, push, manual]

---

## Troubleshooting

### Resetting to a clean state

```bash
# Remove all pre-commit cache
rm -rf .git/hooks/

# Reinstall
pre-commit install

# Run on all files
pre-commit run --all-files
```

### Check which hooks are configured

```bash
pre-commit validate-config
pre-commit validate-manifest
```

### See what would run on commit

```bash
pre-commit run --all-files --dry-run
```

---

## CI Parity

Pre-commit checks mirror GitHub Actions in `.github/workflows/test.yml`:

| Local (pre-commit) | CI (GitHub Actions) |
|--------------------|-------------------|
| black | ✓ (lint job) |
| isort | ✓ (lint job) |
| flake8 | ✓ (lint job) |
| mypy | ✓ (type-check job) |
| pytest (loaders) | ✓ (test job) |
| pytest (transitcov) | ✓ (test job) |

**Benefit:** If pre-commit passes locally, CI will almost certainly pass.

---

## Tips

1. **First time setup slow?** Run tests manually first, then commit:
   ```bash
   cd backend && uv run pytest tests/test_loader_*.py
   cd backend/src/transitcov && uv run pytest tests/
   git add . && git commit -m "message"
   ```

2. **Want to skip just pytest?** Edit `.pre-commit-config.yaml` and set:
   ```yaml
   stages: [manual]  # Requires explicit `pre-commit run --hook-stage manual`
   ```

3. **Multiple developers?** Ensure everyone runs `pre-commit install` so everyone uses same versions.

4. **CI fails but pre-commit passed?** Update hooks:
   ```bash
   pre-commit autoupdate
   pre-commit run --all-files
   ```
