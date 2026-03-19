# UI Automation Testing Project

This project uses Python with pytest and Playwright for browser automation. 
Page Object Model (POM) structure is used for maintainable UI tests.

## Setup

1. Create a Python virtual environment and activate it.
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   playwright install
   ```

## Project Template

If you want to reuse this framework in a new repository, see:

```text
PROJECT_TEMPLATE.md
```

## Running Tests

```sh
pytest -v
```

## CI/CD

This repository includes GitHub Actions workflows for UI automation:

- `UI Smoke`: runs on `push`, `pull_request`, and manual trigger. It executes `tests/test_login.py`.
- `UI Regression`: runs the full pytest suite on manual trigger and every day at `02:00` China time (`18:00 UTC`), then generates an Allure HTML report.

Recommended GitHub repository secrets:

- `JETBAY_TEST_BASE_URL`
- `JETBAY_TEST_LOGIN_EMAIL`
- `JETBAY_TEST_LOGIN_PASSWORD`
- `JETBAY_TEST_DB_NAME`
- `JETBAY_TEST_DB_HOST`
- `JETBAY_TEST_DB_PORT`
- `JETBAY_TEST_DB_USER`
- `JETBAY_TEST_DB_PASSWORD`
- `JETBAY_TEST_DB_DATABASE`
- `JETBAY_TEST_DB_CHARSET`

GitHub setup path:

```text
Repository -> Settings -> Secrets and variables -> Actions
```

After pushing to GitHub, open:

```text
Repository -> Actions
```

Then enable and run the workflows there.

If you want the generated Allure HTML report to be published as a site, also enable:

```text
Repository -> Settings -> Pages -> Build and deployment -> Source = GitHub Actions
```

## Allure Reports

1. Install Python dependency:
   ```sh
   pip install -r requirements.txt
   ```
2. Preferred: use the unified script:
   ```sh
   powershell -ExecutionPolicy Bypass -File .\run_allure_report.ps1
   ```
3. For headless execution:
   ```sh
   powershell -ExecutionPolicy Bypass -File .\run_allure_report.ps1 -Headless
   ```
4. Or run the steps manually:
   ```sh
   pytest --alluredir=allure-results
   powershell -ExecutionPolicy Bypass -File .\generate_allure_report.ps1
   ```
5. Or generate / open the report directly with Allure CLI:
   ```sh
   allure serve allure-results
   ```

If Allure is enabled, failed test screenshots will also be attached to the Allure report.
To keep the `Trend` chart across runs and avoid duplicate test entries in a single report, prefer `run_allure_report.ps1`, because it clears the current `allure-results`, restores the previous `history`, runs pytest, and then generates a fresh report.

## Environments

Environment defaults are stored in `runtime_environments.py`, and can be overridden with environment variables or GitHub Actions secrets.
Built-in proposal route candidates are maintained in `config/search_routes.py`.

- Default environment: `test`
- Switch environment with `TEST_ENV`

Examples:

```sh
set TEST_ENV=test
pytest -v
```

```sh
set TEST_ENV=prod
pytest -v tests/test_login.py -s
```
