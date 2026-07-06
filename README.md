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

In `dev` and `test` environments, SEO-specific pytest cases are not collected by default; run SEO checks separately only when the target environment has the required SEO configuration.

## Local Environment Variables

Local credentials can be stored in `.env.local`. This file is ignored by git and is loaded automatically by `runtime_environments.py`.

```sh
copy .env.example .env.local
```

Then fill in local-only values such as the test login account and database credentials.

## Search Diagnostics

Use the request trace script when you need to inspect the search flow payloads on `dev` or `prod`:

```sh
set TEST_ENV=prod
python scripts/trace_search_requests.py --headless --refresh-results-page --exercise-query-tabs
```

The script records `createSearchId`, `getSearchId`, and `searchList` requests, prints a compact summary in the terminal, and writes the full trace JSON into `artifacts/`.

## CI/CD

This repository includes GitHub Actions workflows for UI automation:

- `UI Smoke`: runs on `push`, `pull_request`, and manual trigger. It executes `tests/test_login.py`.
- `UI Regression`: runs the full pytest suite on manual trigger and every day at `09:00` China time (`01:00 UTC`), then generates an Allure HTML report.

Recommended GitHub repository secrets:

- `JETBAY_TEST_BASE_URL`
- `JETBAY_TEST_LOGIN_EMAIL`
- `JETBAY_TEST_LOGIN_PASSWORD`
- `JETBAY_TEST_FORM_EMAIL` (optional; real mailbox used for form submissions. Falls back to login email.)
- `WECOM_WEBHOOK_URL` (optional, for Enterprise WeChat notifications and report screenshots)

The public repository workflows require the first three secrets above. `WECOM_WEBHOOK_URL` is optional and is used by the regression workflow to send one Enterprise WeChat image containing the enriched Allure overview.

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

## QA Quality Reports

Every pytest run also writes a business-readable QA quality report under:

```text
artifacts/reports/<run_time>/
```

The report set includes:

- `官网回归质量报告_<version>.html`: readable summary with module statistics, failures, skipped cases, and linked evidence.
- `官网回归质量报告_<version>.xlsx`: Excel version for QA/product review.
- `官网回归质量报告_<version>.csv`: test case execution details.
- `quality_results.json`: raw data for follow-up automation.

The report version defaults to `V4.1.1` and can be overridden:

```sh
set QA_REPORT_VERSION=V4.1.1
pytest -v
```

When a new website test version starts, update `QA_REPORT_VERSION` and the default report version to the latest test version before running local or GitHub regression reports.

If a matching issue list exists at `artifacts/问题清单/官网回归问题清单_<version>.csv`, the quality report will merge its fixed/unfixed status into the summary.

The GitHub Actions workflow also injects this quality data into the top of `allure-report/index.html` before uploading and deploying the Allure report. The WeCom screenshot therefore still captures Allure, but the first screen becomes a management summary with pass rate, failed/skipped counts, open issue count, top failed cases, and open issues.

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
