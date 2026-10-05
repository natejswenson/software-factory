"""Documentation regressions use real maintained guides and damaged fixture copies."""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ci_policy, documentation
from software_factory import rules, history

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def check_boundary_contract_ids(self, text):
        def cases(suite):
            for case in suite:
                if isinstance(case, unittest.TestSuite):
                    yield from cases(case)
                else:
                    yield case.id()

        discovered = set(cases(unittest.TestLoader().discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))))
        identifiers = set(re.findall(r'`(tests\.[A-Za-z_][\w.]+)`', text))
        self.assertTrue(identifiers, 'Boundary contract has no test references')
        for identifier in sorted(identifiers):
            self.assertIn(identifier, discovered, f'Undiscovered contract test: {identifier}')
            module, cls, method = identifier.rsplit('.', 2)
            source = ROOT / (module.replace('.', '/') + '.py')
            self.assertIn(f'{cls}.{method}', ci_policy.test_bodies(source.read_text()),
                          f'Contract reference lacks assertion-bearing body: {identifier}')

    def test_boundary_contract_ids_are_discovered_asserting_and_navigation_is_present(self):
        contract = (ROOT / 'docs/development/boundary-tests.md').read_text()
        self.check_boundary_contract_ids(contract)
        first = re.search(r'`(tests\.[A-Za-z_][\w.]+)`', contract)[1]
        with self.assertRaisesRegex(AssertionError, 'Undiscovered contract test'):
            self.check_boundary_contract_ids(contract.replace(first, 'tests.test_documentation.DocumentationTests.test_missing_contract_case'))
        documentation.check_links(ROOT, ('docs/development/boundary-tests.md',))
        for name, link in [('docs/README.md', '](development/boundary-tests.md)'),
                           ('docs/development/testing.md', '](boundary-tests.md)')]:
            self.assertIn(link, (ROOT / name).read_text())
        for name in ('skills/software-factory/SKILL.md', 'skills/software-factory/protocol.md'):
            text = (ROOT / name).read_text()
            self.assertIn('docs/development/boundary-tests.md)', text)
            self.assertIn('asserting', text)
            self.assertIn('Synthetic' if name.endswith('protocol.md') else 'synthetic', text)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in (*documentation.BRANDED, 'docs/branding.json'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def test_real_nested_guides_links_and_pinned_brand_pass(self):
        documentation.check(ROOT)
        self.assertIn('](docs/README.md)', (ROOT / 'README.md').read_text())
        self.assertTrue(all((ROOT / name).is_file() for name in documentation.GUIDES))

    def test_links_validate_fragments_duplicates_and_ignore_fenced_examples(self):
        (self.root / 'guide.md').write_text('# Guide\n## Same\n## Same\n')
        index = self.root / 'index.md'
        index.write_text('# Index\n[Go](guide.md#same-1)\n````markdown\n[Example](absent.md)\n```sh\n# Fake\n```\n````\n')
        documentation.check_links(self.root, ('index.md',))
        self.assertNotIn('fake', documentation.anchors(index.read_text()))
        index.write_text('# Index\n[Go](guide.md#absent)\n')
        with self.assertRaisesRegex(ValueError, 'missing heading'):
            documentation.check_links(self.root, ('index.md',))
        index.write_text('# Index\n[Go](absent.md)\n')
        with self.assertRaisesRegex(ValueError, 'broken local link'):
            documentation.check_links(self.root, ('index.md',))

    def test_links_reject_outside_root_and_decode_spaces(self):
        (self.root / 'with space.md').write_text('# Heading\n')
        index = self.root / 'index.md'
        index.write_text('[Go](with%20space.md#heading)\n')
        documentation.check_links(self.root, ('index.md',))
        index.write_text('[Go](../outside.md)\n')
        with self.assertRaisesRegex(ValueError, 'broken local link'):
            documentation.check_links(self.root, ('index.md',))

    def test_brand_rejects_missing_duplicate_malformed_version_and_content_drift(self):
        path = self.root / 'README.md'
        original = path.read_text()
        block = documentation.REGION.search(original)[0]
        mutations = (original.replace(block, ''), original + '\n' + block,
                     original.replace('sha256:', 'hash:'), original.replace('v0.11.0', 'v0.10.0'),
                     original.replace('CODEX + CLAUDE CODE PLUGIN', 'CHANGED BRAND'))
        for text in mutations:
            with self.subTest(text=text[:80]):
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, 'region'):
                    documentation.check_brand(self.root)
        path.write_text(original)
        documentation.check_brand(self.root)

    def test_receipt_cannot_silently_drop_a_required_region_or_provenance(self):
        path = self.root / 'docs/branding.json'
        original = json.loads(path.read_text())
        value = json.loads(path.read_text())
        value['regions'].pop('README.md')
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'every maintained'):
            documentation.check_brand(self.root)
        original['source_sha256'].pop('brand/tokens.json')
        path.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            documentation.check_brand(self.root)

    def test_missing_guide_or_navigation_is_an_error(self):
        missing = self.root / documentation.GUIDES[-1]
        missing.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing regular'):
            documentation.check(self.root)
        shutil.copy2(ROOT / documentation.GUIDES[-1], missing)
        index = self.root / 'docs/README.md'
        index.write_text(index.read_text().replace('](development/documentation.md)', '](development/testing.md)'))
        with patch.object(documentation, 'check_links'):
            with self.assertRaisesRegex(ValueError, 'lacks navigation'):
                documentation.check(self.root)

    def test_sync_rejects_other_press_version_before_mutating_documents(self):
        press = self.root / 'press'
        press.mkdir()
        (press / 'package.json').write_text('{"version":"0.10.0"}')
        before = (self.root / 'README.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Expected PRESS'):
            documentation.sync_brand(press, self.root)
        self.assertEqual((self.root / 'README.md').read_bytes(), before)

    def test_rules_and_history_bounds_match_current_documentation(self):
        setup = (ROOT / 'docs/user-guide/project-setup.md').read_text()
        commands = (ROOT / 'docs/reference/commands.md').read_text()
        self.assertIn(f'{rules.MAX_FILE // 1024} KiB', setup)
        self.assertIn(f'{rules.MAX_FILES} files', setup)
        self.assertIn(f'{rules.MAX_TOTAL // 1024**2} MiB total', setup)
        self.assertIn(f'History reads at most {history.ATTEMPT_LIMIT} attempts', commands)
        self.assertIn(f'{history.JSON_DEPTH_LIMIT} levels', commands)
