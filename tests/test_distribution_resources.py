"""Archive inspection rejects missing resources and source/build ownership drift."""

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.check_distributions import ROOT, SDIST_REQUIRED, SKILL, TEMPLATES, check


class DistributionResourcesTests(unittest.TestCase):
    def test_archive_inspection_checks_both_skill_and_template_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            wheel = Path(temporary) / "factory.whl"
            source = Path(temporary) / "factory.tar.gz"
            documentation = tuple(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*")
                                  if p.is_file() and p.suffix in {".md", ".json"})
            def build(changed=None, source_changed=None, source_missing=None):
                with zipfile.ZipFile(wheel, "w") as archive:
                    for member, original in (SKILL | TEMPLATES).items():
                        archive.writestr(member, b"stale" if member == changed else (ROOT / original).read_bytes())
                with tarfile.open(source, "w:gz") as archive:
                    for original in (*SKILL.values(), *TEMPLATES, *SDIST_REQUIRED, *documentation):
                        if original == source_missing:
                            continue
                        data = b"stale" if original == source_changed else (ROOT / original).read_bytes()
                        info = tarfile.TarInfo(f"factory/{original}")
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
            build()
            check([wheel, source])
            for changed in (next(iter(SKILL)), next(iter(TEMPLATES))):
                build(changed)
                with self.assertRaisesRegex(ValueError, "resource differs"):
                    check([wheel, source])
            for document in ("docs/user-guide/project-setup.md", "docs/branding.json"):
                build(source_changed=document)
                with self.assertRaisesRegex(ValueError, "Source archive resource differs"):
                    check([wheel, source])
                build(source_missing=document)
                with self.assertRaises(KeyError):
                    check([wheel, source])
            build()
            with tarfile.open(source, "w:gz") as archive:
                info = tarfile.TarInfo("factory/README.md")
                archive.addfile(info, io.BytesIO(b""))
            with self.assertRaises(KeyError):
                check([wheel, source])
            with self.assertRaisesRegex(ValueError, "wheel and source"):
                check([wheel])
