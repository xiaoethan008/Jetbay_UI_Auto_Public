# UI Automation Project Template

Use this project as the baseline when starting a new UI automation repository.

## Recommended Structure

```text
project_root/
|-- AGENTS.md
|-- README.md
|-- pytest.ini
|-- requirements.txt
|-- conftest.py
|-- run_allure_report.ps1
|-- config/
|   |-- environments.py
|-- framework/
|   |-- __init__.py
|   |-- database.py
|   |-- reporting.py
|-- locators/
|   |-- *_locators.py
|-- pages/
|   |-- base_page.py
|   |-- *_page.py
|-- tests/
|   |-- test_*.py
|-- screenshots/
|   |-- failed/
|-- allure-results/
|-- allure-report/
```

## Core Files

### `conftest.py`

Keep all pytest-level wiring here:

- Playwright lifecycle
- browser/page fixtures
- environment metadata for Allure
- failure screenshot hook
- `home_page` fixture
- runtime settings such as `HEADLESS` and `SLOW_MO`

### `config/environments.py`

Store environment-specific settings here:

- `base_url`
- login account and password
- database host, port, db name, username, password

Recommended pattern:

- `test`
- `prod`

Switch environment with `TEST_ENV`.

### `framework/`

Put reusable infrastructure code here:

- `database.py`: MySQL connection and query helpers
- `reporting.py`: screenshot and Allure metadata helpers

Do not put page-specific logic here.

### `pages/`

Put all Page Object classes here:

- `base_page.py`: shared low-level actions
- page files such as `home_page.py`, `search_results_page.py`

Rules:

- keep business flows in page objects
- keep methods scoped to one page or one reusable component
- prefer module/container scoped locators before clicking buttons

### `locators/`

Store locator constants here.

Rules:

- one locator file per page or feature
- keep names stable and explicit
- avoid screen-coordinate based logic

### `tests/`

Store test cases only.

Rules:

- test files should focus on scenario flow and assertions
- move UI operations into page objects
- move raw selectors into locator files

## Current Conventions

### Browser

- default viewport: `1920x1080`
- default navigation timeout: `60000`
- default action timeout: `30000`
- `HEADLESS=true` can be set for headless execution

### Allure

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_allure_report.ps1
```

This script will:

- clear current `allure-results`
- restore `history`
- run pytest with `--alluredir`
- generate a fresh `allure-report`

### Failure Screenshots

Failure screenshots are saved to:

```text
screenshots/failed/
```

### Database

Database helpers should be generic:

- `get_mysql_connection()`
- `fetch_one()`
- `fetch_all()`
- `execute_sql()`

Business-specific queries can be added on top when reuse is clear.

## Locator Strategy

Preferred order:

1. scope to module, dialog, form, or card first
2. use `get_by_role()` inside that scope
3. use `get_by_text()` when role is not enough
4. use relative DOM locators only when semantic locators cannot express the relationship

Avoid:

- absolute coordinates
- viewport-dependent clicks
- global `button` or `input` locators when a dialog/form scope exists

## Test Data Strategy

For unstable frontend search data:

- do not trust database randomization alone
- validate that frontend autocomplete can really find the city
- if not searchable, discard and retry

## New Project Checklist

When starting a new project:

1. copy this directory structure
2. update `config/environments.py`
3. update `README.md`
4. verify Playwright browser install
5. verify Allure CLI and Python plugin
6. verify database dependency such as `PyMySQL`
7. run one smoke test
8. run `run_allure_report.ps1`

## Optional Next Step

If you want a true starter repo, extract these files first:

- `conftest.py`
- `config/environments.py`
- `framework/reporting.py`
- `framework/database.py`
- `pages/base_page.py`
- `run_allure_report.ps1`
- `pytest.ini`
- `requirements.txt`
- `README.md`
- `AGENTS.md`
