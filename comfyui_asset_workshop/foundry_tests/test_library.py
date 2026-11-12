"""Behavior contracts for the Foundry library, independent of a running Comfy server."""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.library import Library
from foundry.preferences import Preferences

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self.library = Library(self.root / "state", self.outputs, busy=lambda: False)

    def package(self, name="Alien", export_id="alien-1", kind="mesh"):
        folder = self.outputs / export_id
        folder.mkdir(exist_ok=True)
        payload = b"preserved asset"
        (folder / "model.glb").write_bytes(payload)
        catalog = {"schema": "mumblebox.asset-catalog/2", "asset_name": name,
                   "export_id": export_id, "created_utc": "2026-10-31T12:00:00Z",
                   "workflow_version": "test", "files": [{"path": "model.glb", "format": "glb",
                   "role": "mesh", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}],
                   "variants": [{"id": "detailed", "measurements": {"triangles": 12}}],
                   "resources": [], "warnings": []}
        (folder / "Metadata").mkdir(exist_ok=True)
        (folder / "Metadata" / "manifest.json").write_text(json.dumps(catalog), encoding="utf-8")
        (folder / "README.md").write_text("Package description.", encoding="utf-8")
        archive = folder.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w") as z:
            for p in folder.rglob("*"):
                if p.is_file(): z.write(p, p.relative_to(folder).as_posix())
        return archive, folder

    def test_import_is_idempotent_and_entry_only_removal_preserves_files(self):
        archive, folder = self.package()
        record = self.library.import_package(archive)
        self.library.import_package(archive)
        self.assertEqual(len(self.library.list("mesh")["items"]), 1)
        preview = self.library.preview_removal("mesh", [record["id"]], False)
        self.library.remove(preview["token"])
        self.assertTrue(archive.is_file())
        self.assertTrue((folder / "model.glb").is_file())
        self.library.import_package(archive)
        self.assertEqual(self.library.list("mesh")["items"], [])

    def test_front_thumbnail_is_owned_copy_and_does_not_change_package_stats(self):
        from PIL import Image
        archive,_=self.package();record=self.library.import_package(archive)
        front=self.outputs/"generated-front.png";Image.new("RGB",(16,16),"blue").save(front)
        self.library.attach_front(record["id"],front)
        updated=self.library.record(record["id"])
        self.assertEqual(updated["file_count"],record["file_count"])
        thumbnail=self.library.file(record["id"],updated["preview_id"])
        self.assertNotEqual(thumbnail,front)
        review=self.library.preview_removal("mesh",[record["id"]],True);self.library.remove(review["token"])
        self.assertTrue(front.is_file())
        self.assertFalse(thumbnail.exists())

    def test_confirmed_file_removal_is_exact_and_keeps_unknown_files(self):
        archive, folder = self.package()
        (folder / "personal-note.txt").write_text("keep", encoding="utf-8")
        record = self.library.import_package(archive)
        preview = self.library.preview_removal("mesh", [record["id"]], True)
        self.assertTrue(any("model.glb" in item for item in preview["files"]))
        self.library.remove(preview["token"])
        self.assertFalse(archive.exists())
        self.assertFalse((folder / "model.glb").exists())
        self.assertTrue((folder / "personal-note.txt").is_file())

    def test_changed_files_invalidate_destructive_confirmation(self):
        archive, folder = self.package()
        record = self.library.import_package(archive)
        preview = self.library.preview_removal("mesh", [record["id"]], True)
        (folder / "model.glb").write_bytes(b"user edited the model")
        with self.assertRaises(ValueError): self.library.remove(preview["token"])
        self.assertTrue(archive.exists())
        self.assertEqual(len(self.library.list("mesh")["items"]), 1)

    def test_busy_runtime_refuses_file_deletion_but_allows_entry_removal(self):
        archive, folder = self.package()
        record = self.library.import_package(archive)
        preview = self.library.preview_removal("mesh", [record["id"]], True)
        self.library.busy = lambda: True
        with self.assertRaises(ValueError): self.library.remove(preview["token"])
        self.assertTrue(archive.exists())

    def test_purge_snapshot_does_not_include_later_exports(self):
        first, _ = self.package(export_id="first")
        a = self.library.import_package(first)
        preview = self.library.preview_removal("mesh", None, False)
        second, _ = self.package(export_id="second")
        b = self.library.import_package(second)
        self.library.remove(preview["token"])
        self.assertEqual([x["id"] for x in self.library.list("mesh")["items"]], [b["id"]])
        self.assertNotEqual(a["id"], b["id"])

    def test_other_kind_cannot_be_removed_and_gallery_excludes_mesh_images(self):
        archive, _ = self.package()
        record = self.library.import_package(archive)
        self.assertEqual(self.library.list("image")["items"], [])
        with self.assertRaises(ValueError):
            self.library.preview_removal("image", [record["id"]], False)

    def test_outside_root_and_archive_traversal_are_rejected(self):
        outside = self.root / "not-output.zip"
        with self.assertRaises(ValueError): self.library.import_package(outside)
        archive, _ = self.package()
        with zipfile.ZipFile(archive, "a") as z: z.writestr("../escaped.txt", "bad")
        with self.assertRaises(ValueError): self.library.import_package(archive)

    def test_pagination_is_bounded_and_file_ids_do_not_allow_path_injection(self):
        archive, _ = self.package()
        record = self.library.import_package(archive)
        with self.assertRaises(ValueError): self.library.list("mesh", limit=5000)
        with self.assertRaises(ValueError): self.library.file(record["id"], "../../secrets")
        page = self.library.list("mesh", limit=1)
        self.assertEqual(page["items"][0]["name"], "Alien")
        self.assertNotIn("archive_path", page["items"][0])

    def test_legacy_package_reports_catalog_problem_without_touching_files(self):
        archive = self.outputs / "legacy.zip"
        with zipfile.ZipFile(archive,"w") as z: z.writestr("mesh.glb",b"original")
        before = archive.read_bytes()
        with self.assertRaisesRegex(ValueError,"older package has no supported catalog"):
            self.library.import_package(archive)
        self.assertEqual(archive.read_bytes(),before)

    def test_video_sync_and_exact_removal_preserve_the_asset_package(self):
        from foundry.video_history import SOURCES, sync

        archive, _ = self.package()
        asset = self.library.import_package(archive)
        names = ("orbit_00001_.mp4", "orbit_00001_.mp4", "orbit/asset_00001_.mp4",
                 "variant-0-aabbccdd/export_00001/motion_00001_.mp4")
        paths = []
        for index, ((state, output, _, workflow), suffix) in enumerate(zip(SOURCES, names)):
            ident = str(index) * 32
            state_dir = self.library.root / state
            state_dir.mkdir()
            (state_dir / (ident + ".json")).write_text(json.dumps({"name": workflow}), encoding="utf-8")
            path = self.outputs / output / ident / suffix
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fixture video")
            paths.append(path)
        stray = paths[0].with_name("personal.mp4")
        stray.write_bytes(b"unmanaged")
        sync(self.library)
        entries = self.library.list("video")["items"]
        self.assertEqual(len(entries), 4)
        self.assertEqual({self.library.file(item["id"], "video") for item in entries}, {path.resolve() for path in paths})
        chosen = next(item for item in entries if item["name"] == "Orbit to Mesh")
        review = self.library.preview_removal("video", [chosen["id"]], True)
        self.assertEqual(review["files"], [str(paths[0].relative_to(self.outputs))])
        self.assertTrue(self.library.remove(review["token"])["ok"])
        self.assertFalse(paths[0].exists())
        self.assertTrue(stray.exists())
        self.assertTrue(archive.exists())
        self.assertEqual(self.library.list("mesh")["items"][0]["id"], asset["id"])
        sync(self.library)
        self.assertEqual(len(self.library.list("video")["items"]), 3)
        paths[0].write_bytes(b"regenerated video with a new identity")
        sync(self.library)
        self.assertEqual(len(self.library.list("video")["items"]), 4)
        self.assertNotIn(chosen["id"], {entry["id"] for entry in self.library.list("video")["items"]})

    def test_preferences_reject_tokens_and_inactive_profiles(self):
        prefs = Preferences(self.root / "prefs.json")
        prefs.update({"theme": "dark", "language": "en"})
        self.assertEqual(prefs.read()["theme"], "dark")
        for patch in ({"token": "secret"}, {"memory_profile": "8gb"}, {"language": "de"}):
            with self.assertRaises(ValueError): prefs.update(patch)
        self.assertNotIn("secret", (self.root / "prefs.json").read_text())

if __name__ == "__main__": unittest.main()
