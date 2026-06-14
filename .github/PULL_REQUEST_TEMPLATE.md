## What does this PR do?

<!-- Short summary of the change and why it's needed. Link the issue if one exists: Fixes #123 -->

## How was it tested?

<!-- e.g. ran pytest against the Docker stack, manual steps in the UI, added tests -->

## Checklist

- [ ] One focused change (split unrelated work into separate PRs)
- [ ] Lint passes: `ruff check app services tests alembic scripts celery_app.py --select E9,F,W --ignore F403,F405`
- [ ] Tests pass: `API_BASE=http://localhost:6000 pytest`
- [ ] Frontend type-checks (if UI changed): `cd opama-ui && npx tsc --noEmit`
- [ ] Screenshots attached for UI changes
- [ ] New endpoints follow project conventions (auth dependency, ownership checks, static-before-dynamic routes)
