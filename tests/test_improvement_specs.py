"""Keep hand-authored improvement requirements complete and navigable."""

import re
import tempfile
import unittest
from pathlib import Path

from scripts import documentation

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    '0010-integration-readiness.md',
    '0011-focused-feedback.md',
    '0012-boundary-test-contracts.md',
    '0013-prd-intake.md',
    '0014-guided-resume.md',
    '0015-documentation-contracts.md',
)
PRD_SECTIONS = (
    'Problem and users', 'Desired outcome', 'Scope', 'Non-goals', 'User workflow',
    'Requirements', 'Acceptance criteria', 'Constraints and compatibility',
    'Dependencies', 'Verification', 'Risks and open questions', 'Delivery and follow-up',
)
DESIGN_SECTIONS = (
    'Problem, evidence and decisions', 'Interface and user experience',
    'Architecture and implementation contract', 'Exact file responsibilities',
    'Compatibility and failure cases', 'Implementation sequence',
    'Acceptance criteria', 'Verification and review', 'Rollout and recovery',
)
REPORT = 'design/run-review-2026-10-05.md'


def criteria(text):
    match = re.search(r'^## Acceptance criteria\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Missing acceptance criteria')
    items = re.findall(r'^- \*\*(AC\d+):\*\* (.*?)(?=^- \*\*AC|\Z)', match[1], re.M | re.S)
    values = [(label, ' '.join(body.split())) for label, body in items]
    if not values or [label for label, _ in values] != [f'AC{i}' for i in range(1, len(values) + 1)]:
        raise ValueError('Acceptance criteria must be nonempty and contiguous')
    return values


def check_pair(prd, design):
    if criteria(prd) != criteria(design):
        raise ValueError('PRD/design acceptance criteria differ')


class ImprovementSpecificationTests(unittest.TestCase):
    def test_six_pairs_have_complete_sections_pending_status_and_equal_criteria(self):
        for name in PAIRS:
            with self.subTest(pair=name):
                prd = (ROOT / 'prd' / name).read_text()
                design = (ROOT / 'design' / name).read_text()
                for content, sections in ((prd, PRD_SECTIONS), (design, DESIGN_SECTIONS)):
                    for section in sections:
                        self.assertEqual(content.count(f'\n## {section}\n'), 1)
                    self.assertIn('implementation pending', content)
                    self.assertIn('84f387e', content)
                    self.assertIn('python3 scripts/verify.py tests', content)
                    self.assertIn('python3 scripts/verify.py source', content)
                self.assertIn(f'](../design/{name})', prd)
                self.assertIn(f'](../prd/{name})', design)
                self.assertIn('Status: ready;', prd)
                self.assertIn('Status: ready for factory planning;', design)
                check_pair(prd, design)
                self.assertEqual(len(criteria(prd)), 5)

    def test_all_specification_links_resolve_and_indexes_expose_each_pair(self):
        names = tuple(f'{folder}/{name}' for folder in ('prd', 'design') for name in PAIRS)
        documentation.check_links(ROOT, (*names, REPORT, 'prd/README.md', 'design/README.md'))
        for folder in ('prd', 'design'):
            index = (ROOT / folder / 'README.md').read_text()
            self.assertIn('run-review-2026-10-05.md)', index)
            for name in PAIRS:
                self.assertIn(f']({name})', index)

    def test_evidence_inventory_and_observation_limits_are_preserved(self):
        report = (ROOT / REPORT).read_text()
        inventory = report.split('## Run inventory\n', 1)[1].split('## Findings', 1)[0]
        rows = [line for line in inventory.splitlines() if line.startswith('| ')][1:]
        self.assertEqual(len(rows), 27)
        self.assertEqual(sum(int(row.split('|')[3].strip()) for row in rows), 48)
        self.assertEqual(sum('| done |' in row for row in rows), 23)
        self.assertIn('ACTIVITY_UNREADABLE_OR_INVALID', report)
        self.assertIn('not task wall time', report)
        self.assertIn('speedup unmeasured', report)
        self.assertIn('omission not observed', report)
        self.assertIn('not present\nremote merge/release state', report)
        for identifier in range(1, 7):
            self.assertEqual(report.count(f'### E{identifier} —'), 1)

    def test_new_public_documents_contain_no_private_runtime_paths_or_receipt_bodies(self):
        names = [ROOT / REPORT, *(ROOT / folder / name for folder in ('prd', 'design') for name in PAIRS)]
        for path in names:
            with self.subTest(path=path.name):
                content = path.read_text()
                self.assertNotRegex(content, r'/Users/|/private/tmp/|\.git/factory/runs/')
                self.assertNotRegex(content, r'(?i)"(?:capture_id|event_id|configHash)"\s*:')
                self.assertNotRegex(content, r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')

    def test_damaged_criteria_and_links_are_rejected(self):
        name = PAIRS[0]
        prd = (ROOT / 'prd' / name).read_text()
        design = (ROOT / 'design' / name).read_text()
        with self.assertRaisesRegex(ValueError, 'differ'):
            check_pair(prd, design.replace('**AC1:** Integration', '**AC1:** Changed integration', 1))
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            criteria(prd.replace('**AC2:**', '**AC9:**', 1))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'guide.md').write_text('# Guide\n[Design](missing.md)\n')
            with self.assertRaisesRegex(ValueError, 'broken local link'):
                documentation.check_links(root, ('guide.md',))
