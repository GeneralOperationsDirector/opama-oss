# Scheduled Task System - Pokemon TCG Catalog Auto-Sync

This document describes the automated catalog synchronization system built with Celery + Redis.

## Overview

opama now includes an automated catalog-sync system that:
- **Discovers** new Pokemon TCG sets from the official API every 3 days
- **Syncs** new sets automatically without manual intervention
- **Tracks** synchronization history and status
- **Provides** manual controls for on-demand syncing

## Architecture

```
┌─────────────────┐
│  Celery Beat    │  Scheduler (runs every 3 days at 2 AM UTC)
│   (Container)   │
└────────┬────────┘
         │ Schedules task
         ▼
┌─────────────────┐
│   Redis Broker  │  Message queue
│   (Container)   │
└────────┬────────┘
         │ Queues task
         ▼
┌─────────────────┐
│ Celery Worker   │  Executes sync tasks
│   (Container)   │  ├─ Discovers new sets
│                 │  ├─ Fetches cards from API
│                 │  └─ Imports to PostgreSQL
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PostgreSQL DB  │  Stores cards, sets, sync logs
│   (Container)   │
└─────────────────┘
```

## Services

### 1. Celery Worker (`celery-worker`)
**Purpose:** Executes async tasks (sync operations)

**Container:** `pokemon-celery-worker`

**Command:**
```bash
celery -A celery_app worker --loglevel=info --concurrency=2
```

**Configuration:**
- **Concurrency:** 2 workers
- **Time Limit:** 1 hour per task
- **Prefetch:** 1 task at a time (sequential processing)

### 2. Celery Beat (`celery-beat`)
**Purpose:** Schedules periodic tasks

**Container:** `pokemon-celery-beat`

**Schedule:**
- **Task:** `check_and_sync_catalog`
- **Frequency:** Every 3 days at 2 AM UTC
- **Trigger:** `crontab(hour=2, minute=0, day_of_month='*/3')`

### 3. Flower (`flower`)
**Purpose:** Web-based monitoring dashboard

**Container:** `pokemon-flower`

**Access:** http://localhost:5555

**Features:**
- Real-time task monitoring
- Worker status
- Task history
- Success/failure rates

### 4. Redis (`redis`)
**Purpose:** Message broker and result backend

**Container:** `pokemon-redis`

**Port:** 6379

## Tasks

### Task 1: `check_and_sync_catalog`

**Type:** Scheduled (every 3 days) + Manual trigger

**What it does:**
1. Queries Pokemon TCG API for all sets
2. Compares with local database
3. Identifies NEW sets not in database
4. Syncs each new set (fetch + import cards)
5. Records results in `CatalogSyncLog`

**Configuration:**
```python
# In celery_app.py
beat_schedule = {
    'check-and-sync-catalog-every-3-days': {
        'task': 'services.catalog.tasks.check_and_sync_catalog',
        'schedule': crontab(hour=2, minute=0, day_of_month='*/3'),
    }
}
```

**Return Value:**
```json
{
  "sync_log_id": 1,
  "sets_discovered": 2,
  "sets_synced": 2,
  "sets_failed": 0,
  "status": "success",
  "new_sets": ["me1", "me2"]
}
```

### Task 2: `sync_single_set`

**Type:** Worker task (called by check_and_sync_catalog or manually)

**What it does:**
1. Fetches set info from API
2. Creates/updates Set record
3. Fetches all cards for the set
4. Creates/updates Card records (idempotent)
5. Updates `SetSyncStatus`

**Retry Strategy:**
- **Max Retries:** 5
- **Backoff:** Exponential (5min, 10min, 20min, 40min, 80min)

**Return Value:**
```json
{
  "set_id": "me1",
  "success": true,
  "cards_count": 132,
  "error": null
}
```

## Manual Controls (REST API)

### Trigger Full Sync

Manually discover and sync all new sets:

```bash
curl -X POST http://localhost:8008/cards/sync/trigger
```

**Response:**
```json
{
  "message": "Catalog sync completed",
  "sync_type": "manual",
  "sync_log_id": 5,
  "sets_discovered": 2,
  "sets_synced": 2,
  "sets_failed": 0,
  "status": "success",
  "new_sets": ["me1", "me2"]
}
```

### Sync Specific Set

Re-sync or update a specific set:

```bash
curl -X POST http://localhost:8008/cards/sync/set/me1
```

**Response:**
```json
{
  "set_id": "me1",
  "success": true,
  "cards_count": 132,
  "last_synced_at": "2025-11-26T18:30:15"
}
```

### Check Sync Status

View recent sync history:

```bash
curl http://localhost:8008/cards/sync/status?limit=5
```

**Response:**
```json
{
  "syncs": [
    {
      "id": 1,
      "sync_type": "manual",
      "started_at": "2025-11-26T18:30:00",
      "completed_at": "2025-11-26T18:35:30",
      "status": "success",
      "sets_discovered": 2,
      "sets_synced": 2,
      "sets_failed": 0,
      "error_message": null
    }
  ],
  "count": 1
}
```

### View Set Sync Status

See which sets have been synced:

```bash
curl http://localhost:8008/cards/sync/sets
```

**Response:**
```json
{
  "sets": [
    {
      "set_id": "me1",
      "last_synced_at": "2025-11-26T18:32:15",
      "cards_count": 132,
      "sync_status": "success",
      "error_details": null
    }
  ],
  "count": 169
}
```

## Starting & Stopping

### Start All Services (Development Mode)

```bash
# Start infrastructure + backend + celery + frontend
docker compose --profile dev up -d

# View logs
docker compose logs -f celery-worker celery-beat flower
```

### Start Only Celery Services

```bash
# Start just the task system
docker compose up -d redis postgres celery-worker celery-beat flower
```

### Stop Celery Services

```bash
docker compose stop celery-worker celery-beat flower
```

### Restart After Code Changes

```bash
# Rebuild and restart
docker compose --profile dev up -d --build celery-worker celery-beat
```

## Monitoring

### Flower Dashboard

Access: http://localhost:5555

**Features:**
- Active tasks (running now)
- Task history (completed, failed)
- Worker status (online/offline)
- Task execution times
- Success/failure rates

### Database Logs

Check sync history directly:

```sql
-- Recent syncs
SELECT * FROM catalogsynclog ORDER BY started_at DESC LIMIT 10;

-- Set sync status
SELECT * FROM setsyncstatus ORDER BY last_synced_at DESC;
```

### Container Logs

```bash
# Worker logs
docker compose logs -f celery-worker

# Beat scheduler logs
docker compose logs -f celery-beat

# All logs
docker compose logs -f
```

## Configuration

### Environment Variables

Add to `.env.local`:

```bash
# Database
DATABASE_URL=postgresql://pokemon_user:pokemon_pass@localhost:5433/pokemon_tcg

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Pokemon TCG API (optional - works without but with rate limits)
POKEMON_TCG_API_KEY=your_api_key_here
```

### Schedule Adjustment

To change sync frequency, edit `celery_app.py`:

```python
# Current: Every 3 days at 2 AM UTC
'schedule': crontab(hour=2, minute=0, day_of_month='*/3')

# Daily at 2 AM:
'schedule': crontab(hour=2, minute=0)

# Weekly on Mondays at 2 AM:
'schedule': crontab(hour=2, minute=0, day_of_week=1)

# Every 6 hours:
'schedule': crontab(minute=0, hour='*/6')
```

Then restart celery-beat:
```bash
docker compose restart celery-beat
```

### Rate Limiting

The Pokemon TCG API client includes rate limiting. To adjust:

Edit `services/catalog/sync_service.py`:

```python
# Default: 1 second between requests
service = CatalogSyncService(session, rate_limit_delay=1.0)

# Faster (if you have API key):
service = CatalogSyncService(session, rate_limit_delay=0.5)

# Slower (more conservative):
service = CatalogSyncService(session, rate_limit_delay=2.0)
```

## Troubleshooting

### Problem: Tasks not running

**Check:**
1. Are containers running?
   ```bash
   docker compose ps
   ```

2. Is Redis accessible?
   ```bash
   docker exec pokemon-redis redis-cli ping
   # Should return: PONG
   ```

3. Are workers registered?
   - Open Flower: http://localhost:5555
   - Check "Workers" tab

**Solution:**
```bash
docker compose restart celery-worker celery-beat
```

### Problem: Sync fails with API timeout

**Cause:** Pokemon TCG API is slow or unresponsive

**Solution:**
1. Check API status: https://api.pokemontcg.io/v2/sets
2. Increase timeout in `pokemon_tcg_client.py` (default: 60s)
3. Wait and let Celery retry automatically

### Problem: Duplicate cards after sync

**Cause:** This shouldn't happen - sync uses idempotent logic

**Check:**
```sql
SELECT id, COUNT(*) FROM card GROUP BY id HAVING COUNT(*) > 1;
```

**Solution:**
- Report issue with details
- Re-run sync for affected set:
  ```bash
  curl -X POST http://localhost:8008/cards/sync/set/{set_id}
  ```

### Problem: Database connection errors

**Check:**
```bash
docker compose logs postgres
```

**Solution:**
```bash
# Restart database
docker compose restart postgres

# Wait for health check
docker compose ps postgres
```

### Problem: Celery worker crashes

**Check logs:**
```bash
docker compose logs celery-worker
```

**Common causes:**
- Out of memory (increase Docker memory limit)
- Database connection pool exhausted
- Unhandled exception in task

**Solution:**
```bash
# Restart worker
docker compose restart celery-worker

# If persists, check resource limits
docker stats
```

## Testing

### Test Manual Sync

```bash
# 1. Trigger sync
curl -X POST http://localhost:8008/cards/sync/trigger

# 2. Check status
curl http://localhost:8008/cards/sync/status

# 3. Verify in database
docker exec -it pokemon-postgres psql -U pokemon_user -d pokemon_tcg
SELECT COUNT(*) FROM card;
SELECT * FROM catalogsynclog ORDER BY id DESC LIMIT 1;
```

### Test Scheduled Task (Without Waiting 3 Days)

```bash
# Manually invoke the scheduled task
docker exec pokemon-celery-worker celery -A celery_app call services.catalog.tasks.check_and_sync_catalog
```

### Test Celery Connection

```python
# In Python shell
from celery_app import celery_app

# Check broker connection
celery_app.connection().ensure_connection(max_retries=3)
print("✓ Connected to Redis")

# Check registered tasks
print(celery_app.tasks.keys())
```

## Performance

### Current Configuration

- **Sync Frequency:** Every 3 days
- **API Rate Limit:** 1 request/second
- **Worker Concurrency:** 2 tasks simultaneously
- **Average sync time:** ~5 minutes per set (depending on card count)

### Optimization Options

1. **Increase concurrency** (if API allows):
   ```yaml
   # In docker-compose.yml
   command: celery -A celery_app worker --concurrency=4
   ```

2. **Parallel set syncing** (future enhancement):
   - Modify `check_and_sync_catalog` to use `.delay()` for parallel execution
   - Each set syncs in separate worker

3. **Reduce API calls** (if needed):
   - Only sync sets released in last N months
   - Skip re-syncing existing sets unless forced

## Database Tables

### `catalogsynclog`

Tracks sync runs:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| sync_type | VARCHAR | 'scheduled', 'manual', 'initial' |
| started_at | TIMESTAMP | When sync started |
| completed_at | TIMESTAMP | When sync finished |
| status | VARCHAR | 'running', 'success', 'partial', 'failed' |
| sets_discovered | INTEGER | New sets found |
| sets_synced | INTEGER | Successfully synced |
| sets_failed | INTEGER | Failed to sync |
| error_message | TEXT | Error details if failed |

### `setsyncstatus`

Tracks per-set sync status:

| Column | Type | Description |
|--------|------|-------------|
| set_id | VARCHAR | Set ID (primary key) |
| last_synced_at | TIMESTAMP | Last sync time |
| cards_count | INTEGER | Number of cards synced |
| sync_status | VARCHAR | 'success', 'failed', 'pending' |
| error_details | TEXT | Error message if failed |

## Security Notes

- **No authentication** on sync endpoints (currently)
- **Before production:** Add auth middleware to `/sync/*` endpoints
- **API key:** Keep `POKEMON_TCG_API_KEY` in `.env.local` (not committed)
- **Database:** PostgreSQL uses strong password (from `.env`)

## Next Steps / Future Enhancements

1. **Price Integration (Phase 2)**
   - Add TCGPlayer API integration
   - Schedule price refresh tasks
   - Track historical price data

2. **Retry Logic Improvements**
   - Dead letter queue for persistent failures
   - Alert notifications on repeated failures

3. **UI Dashboard**
   - React component for sync management
   - Real-time sync progress display
   - Manual trigger buttons

4. **Monitoring & Alerts**
   - Prometheus metrics export
   - Slack/email alerts on failures
   - Performance dashboards

## Support

For issues or questions:
1. Check logs: `docker compose logs -f celery-worker`
2. Check Flower dashboard: http://localhost:5555
3. Review this documentation
4. Check plan file: `.claude/plans/floating-seeking-orbit.md`

---

**Last Updated:** 2025-11-26
**System Version:** Phase 1 - Catalog Sync (Complete)
