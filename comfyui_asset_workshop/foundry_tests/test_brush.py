"""Regression coverage for first-use installation of the pinned Brush package."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.workflows.orbit_with_splats import brush


class BrushSetupTests(TestCase):
    def test_verified_install_reuses_existing_executable_and_repairs_managed_copy(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("brush_app.exe", b"verified brush")
            archive.writestr("LICENSE", b"upstream license")
        payload = buffer.getvalue()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "brush_app.exe"
            with patch.multiple(brush, ARCHIVE_SIZE=len(payload), ARCHIVE_SHA256=sha256(payload).hexdigest(),
                                BRUSH_SHA256=sha256(b"verified brush").hexdigest()), \
                 patch.object(brush, "brush_path", return_value=target), \
                 patch.object(brush, "can_install", return_value=True), \
                 patch.dict(brush.os.environ, {"MUMBLEBOX_BRUSH": ""}), \
                 patch.object(brush, "urlopen", side_effect=lambda *args, **kwargs: BytesIO(payload)) as fetch:
                self.assertEqual(brush.ensure_brush(), target)
                self.assertEqual(target.read_bytes(), b"verified brush")
                self.assertEqual(brush.ensure_brush(), target)
                self.assertEqual(fetch.call_count, 1)
                target.write_bytes(b"broken managed copy")
                self.assertEqual(brush.ensure_brush(), target)
                self.assertEqual(target.read_bytes(), b"verified brush")
                self.assertEqual(fetch.call_count, 2)

    def test_bad_or_cancelled_download_leaves_no_installed_file(self):
        payload = b"wrong archive"
        with TemporaryDirectory() as directory:
            target = Path(directory) / "brush_app.exe"
            with patch.multiple(brush, ARCHIVE_SIZE=len(payload), ARCHIVE_SHA256="0" * 64), \
                 patch.object(brush, "brush_path", return_value=target), \
                 patch.object(brush, "can_install", return_value=True), \
                 patch.dict(brush.os.environ, {"MUMBLEBOX_BRUSH": ""}), \
                 patch.object(brush, "urlopen", side_effect=lambda *args, **kwargs: BytesIO(payload)):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    brush.ensure_brush()
                with self.assertRaises(InterruptedError):
                    brush.ensure_brush(cancelled=lambda: True)
                self.assertEqual(list(target.parent.iterdir()), [])
