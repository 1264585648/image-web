# ProductShot AI E2E tests

These tests exercise the deployed HTTP app end to end:

- static frontend shell
- health and template APIs
- image upload
- async generation and task polling
- generated asset URLs
- task zip download
- history lookup
- retry guard for non-failed tasks

Run against local development:

```bash
pip install -r backend/requirements.txt -r requirements-test.txt
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
pytest tests/e2e
```

Run against a deployed server:

```bash
E2E_BASE_URL=http://34.134.109.205:8000 pytest tests/e2e
```
