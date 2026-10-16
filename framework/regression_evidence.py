"""Per-case evidence for persistent mutations and conditional regression."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from framework.exploration_journal import ExplorationJournal
from runtime_environments import get_current_environment_name


@pytest.fixture
def case_evidence(request):
    env = get_current_environment_name()
    configured = os.environ.get('WEBSITE_GAPS_RUN')
    root = Path(configured) if configured else Path('artifacts/临时文件/官网回归/website-case-runs') / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    module = request.path.stem
    suffix = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:12] + '-' + uuid4().hex[:8]
    journal = ExplorationJournal.create(root / 'case-evidence' / env / module / suffix, environment=env, module=module)
    case_id = request.node.nodeid
    if len(case_id) > 128:
        case_id = case_id[:105] + ':' + suffix
    step = journal.begin(case_id, expected='Execute linked business assertions with explicit verification layer', next_action='Run once; preserve baseline before mutation')
    journal.step_id = step
    yield journal
    reports = [getattr(request.node, 'rep_' + phase, None) for phase in ('setup', 'call', 'teardown')]
    failed = any(r is not None and r.failed for r in reports)
    skipped = any(r is not None and r.skipped for r in reports)
    journal.json_evidence(step, {'nodeid': request.node.nodeid, 'failed': failed, 'skipped': skipped})
    journal.finish(step, status='failed' if failed else 'blocked' if skipped else 'passed', actual='Assertions failed' if failed else 'Conditional prerequisite unavailable' if skipped else 'All assertions passed')
