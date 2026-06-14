"""
Celery Tasks for Catalog Synchronization

These tasks run asynchronously to sync Pokemon TCG catalog data from the API.

Tasks:
- check_and_sync_catalog: Scheduled task that discovers and syncs new sets
- sync_single_set: Worker task that syncs a specific set

Usage:
    # Manual trigger
    from opama_pokemon_tcg.catalog.tasks import check_and_sync_catalog
    result = check_and_sync_catalog.delay()

    # Check result
    print(result.get())
"""

from typing import Dict
from celery import Task
from celery.schedules import crontab
from sqlmodel import Session

from services.shared.database import engine
from opama_pokemon_tcg.catalog.sync_service import CatalogSyncService

# Merged into celery_app.conf by celery_app.py's plugin-discovery loop.
TASK_ROUTES = {
    'opama_pokemon_tcg.catalog.tasks.*': {'queue': 'catalog'},
}

# Runs check_and_sync_catalog every 3 days at 2 AM UTC.
BEAT_SCHEDULE = {
    'check-and-sync-catalog-every-3-days': {
        'task': 'opama_pokemon_tcg.catalog.tasks.check_and_sync_catalog',
        'schedule': crontab(
            hour=2,       # 2 AM
            minute=0,     # On the hour
            day_of_month='*/3'  # Every 3 days
        ),
        'options': {
            'expires': 7200,  # Task expires after 2 hours if not executed
        }
    },
}


# Import celery app (will be created in celery_app.py)
# This is imported at the bottom to avoid circular imports
def get_celery_app():
    """Lazy import celery app to avoid circular dependency."""
    from celery_app import celery_app
    return celery_app


class DatabaseTask(Task):
    """
    Base task that provides database session management.

    This ensures each task gets a fresh database session and
    properly commits/rolls back transactions.
    """

    def __call__(self, *args, **kwargs):
        """Execute task with database session."""
        # Each task gets its own session
        return super().__call__(*args, **kwargs)


# Task 1: Main scheduled task
def check_and_sync_catalog_impl(self) -> Dict:
    """
    Main catalog sync task - discovers and syncs new sets.

    This is the scheduled task that runs every 3 days.
    It:
    1. Discovers new sets from the API
    2. Spawns sync_single_set tasks for each new set
    3. Tracks overall sync status in CatalogSyncLog

    Returns:
        Dictionary with sync results:
        - sync_log_id: ID of the CatalogSyncLog entry
        - sets_discovered: Number of new sets found
        - sets_synced: Number successfully synced
        - sets_failed: Number that failed
        - status: Overall status
    """
    with Session(engine) as session:
        service = CatalogSyncService(session)

        # Create sync log
        log = service.create_sync_log('scheduled')

        try:
            # Discover new sets
            new_sets = service.discover_new_sets()
            log.sets_discovered = len(new_sets)
            session.add(log)
            session.commit()

            if not new_sets:
                # No new sets - mark as success
                service.finalize_sync_log(log, 'success')
                return {
                    'sync_log_id': log.id,
                    'sets_discovered': 0,
                    'sets_synced': 0,
                    'sets_failed': 0,
                    'status': 'success',
                    'message': 'No new sets to sync'
                }

            # Sync each set
            success_count = 0
            fail_count = 0

            for set_id in new_sets:
                try:
                    # Call sync_single_set synchronously for simplicity
                    # In production, you might use .delay() for parallel execution
                    success = service.sync_set(set_id)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    print(f"Error syncing {set_id}: {e}")
                    fail_count += 1

            # Update sync log
            log.sets_synced = success_count
            log.sets_failed = fail_count

            if fail_count == 0:
                status = 'success'
            elif success_count > 0:
                status = 'partial'
            else:
                status = 'failed'

            service.finalize_sync_log(log, status)

            return {
                'sync_log_id': log.id,
                'sets_discovered': len(new_sets),
                'sets_synced': success_count,
                'sets_failed': fail_count,
                'status': status,
                'new_sets': new_sets
            }

        except Exception as e:
            # Mark sync as failed
            service.finalize_sync_log(log, 'failed', str(e))
            raise


def check_and_sync_catalog():
    """
    Wrapper function that will be registered as Celery task.

    This is separated to allow for testing without Celery.
    """
    # Create a dummy self for compatibility
    class DummySelf:
        pass
    return check_and_sync_catalog_impl(DummySelf())


# Task 2: Worker task for syncing individual sets
def sync_single_set_impl(self, set_id: str) -> Dict:
    """
    Sync a single set from the API to the database.

    This task can be called:
    - By check_and_sync_catalog for newly discovered sets
    - Manually via API endpoint for on-demand syncs
    - For retry of failed syncs

    Args:
        set_id: Pokemon TCG set ID (e.g., "me1", "sv10")

    Returns:
        Dictionary with sync results:
        - set_id: The set that was synced
        - success: Whether sync succeeded
        - cards_count: Number of cards synced
        - error: Error message if failed

    Raises:
        Exception: On sync failure (triggers Celery retry)
    """
    with Session(engine) as session:
        service = CatalogSyncService(session)

        try:
            success = service.sync_set(set_id)

            if not success:
                # Sync reported failure
                raise Exception(f"Sync service reported failure for {set_id}")

            # Get cards count from sync status
            from opama_pokemon_tcg.catalog.models import SetSyncStatus
            sync_status = session.get(SetSyncStatus, set_id)
            cards_count = sync_status.cards_count if sync_status else 0

            return {
                'set_id': set_id,
                'success': True,
                'cards_count': cards_count,
                'error': None
            }

        except Exception as e:
            error_msg = str(e)
            print(f"Error syncing {set_id}: {error_msg}")

            # For Celery retry mechanism
            if hasattr(self, 'retry'):
                # Retry with exponential backoff (5min, 10min, 20min, 40min, 80min)
                raise self.retry(exc=e, countdown=300 * (2 ** self.request.retries))

            return {
                'set_id': set_id,
                'success': False,
                'cards_count': 0,
                'error': error_msg
            }


def sync_single_set(set_id: str):
    """
    Wrapper function that will be registered as Celery task.

    Args:
        set_id: Pokemon TCG set ID to sync
    """
    class DummySelf:
        pass
    return sync_single_set_impl(DummySelf(), set_id)


# Register tasks with Celery when this module is imported by celery_app
def register_tasks(celery_app):
    """
    Register tasks with the Celery application.

    This function is called from celery_app.py during initialization.
    """

    @celery_app.task(
        bind=True,
        name='opama_pokemon_tcg.catalog.tasks.check_and_sync_catalog',
        max_retries=3,
        default_retry_delay=600  # 10 minutes
    )
    def _check_and_sync_catalog(self):
        return check_and_sync_catalog_impl(self)

    @celery_app.task(
        bind=True,
        name='opama_pokemon_tcg.catalog.tasks.sync_single_set',
        max_retries=5,
        default_retry_delay=300  # 5 minutes
    )
    def _sync_single_set(self, set_id: str):
        return sync_single_set_impl(self, set_id)

    return _check_and_sync_catalog, _sync_single_set
