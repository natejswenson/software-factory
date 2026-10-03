"""Python-only runtime proof independent of globally installed Node/npm."""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

from software_factory.delivery import deliver
from tests.support import FactoryCase


class PackagingTests(FactoryCase):
    def test_real_local_lifecycle_with_node_and_npm_absent(self):
        f = self.fixture()
        bin_dir = f.root / "python-only-bin"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git"))
        with patch.dict(os.environ, {"PATH": str(bin_dir)}):
            self.assertIsNone(shutil.which("node"))
            self.assertIsNone(shutil.which("npm"))
            run = self.reviewed(f)
            done = deliver(run["run"])
            self.assertEqual(done["phase"], "done")
            self.assertEqual(self.summary(done)["delivery"], done["delivery"])
            self.assertTrue((Path(run["run"]) / "delivery.json").is_file())
