"""Catalog-backed history, bounded paging and reviewed removal with persistent tombstones."""
from contextlib import contextmanager
import hashlib
import json
import secrets
import shutil
import sqlite3
import threading
import time
import zipfile
from pathlib import Path

from .artifacts import digest, fingerprint, owned_path, relative_name, remove_exact

class Library:
    def __init__(self, state_root, output_root, busy=lambda: False):
        self.root = Path(state_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_root = Path(output_root).resolve()
        self.busy = busy
        self.lock = threading.RLock()
        self.database = self.root / "library.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records(
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, created TEXT NOT NULL,
                    revision TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS records_kind_created ON records(kind, removed, created DESC, id DESC);
                CREATE TABLE IF NOT EXISTS files(
                    record_id TEXT NOT NULL, id TEXT NOT NULL, path TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(record_id,id));
                CREATE INDEX IF NOT EXISTS files_path ON files(path);
                CREATE TABLE IF NOT EXISTS reviews(token TEXT PRIMARY KEY, expires REAL NOT NULL, data TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally:
            db.close()

    @staticmethod
    def kind(value):
        if value not in ("mesh", "image", "video"): raise ValueError("Choose mesh history, video history or the image gallery.")
        return value

    def import_package(self, archive):
        archive = owned_path(self.output_root, archive)
        if archive.suffix.lower() != ".zip" or not archive.is_file():
            raise ValueError("Choose an existing Foundry asset package.")
        folder = owned_path(self.output_root, archive.with_suffix(""))
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > 2000: raise ValueError("The package has too many entries.")
            names = [str(relative_name(item.filename)) for item in entries if not item.is_dir()]
            if len(names) != len(set(n.casefold() for n in names)):
                raise ValueError("Package filenames collide.")
            if "Metadata/manifest.json" not in names:
                raise ValueError("This older package has no supported catalog. Choose a current Foundry package; its files have not been changed.")
            info = z.getinfo("Metadata/manifest.json")
            if info.file_size > 4 * 1024 * 1024: raise ValueError("The package catalog is too large.")
            catalog = json.loads(z.read(info))
            if catalog.get("schema") != "mumblebox.asset-catalog/2":
                raise ValueError("This is not a supported Foundry package catalog.")
            export_id = catalog.get("export_id")
            if not isinstance(export_id, str) or not export_id or len(export_id) > 128:
                raise ValueError("The package export identity is missing.")
            record_id = hashlib.sha256(("mesh:" + export_id).encode()).hexdigest()[:32]
            with self.connect() as db:
                previous = db.execute("SELECT data, removed FROM records WHERE id=?", (record_id,)).fetchone()
                if previous:
                    # Replay never resurrects a user-removed history entry.
                    return self.public(json.loads(previous["data"]))
            catalog_files = catalog.get("files", [])
            if not isinstance(catalog_files, list) or len(catalog_files) > 2000:
                raise ValueError("The catalog file inventory is invalid.")
            for item in catalog_files:
                if str(relative_name(item["path"])) not in names:
                    raise ValueError("The package is missing a cataloged file.")
            files = [{"id": "archive", "path": str(archive), "name": archive.name,
                      "download": True, "role": "archive", "fingerprint": fingerprint(archive)}]
            for name in names:
                path = owned_path(self.output_root, folder / name)
                # A missing unpacked copy does not prevent downloading the archive.
                if path.is_file():
                    files.append({"id": hashlib.sha256(name.encode()).hexdigest()[:24],
                                  "path": str(path), "name": name, "role": "package",
                                  "fingerprint": fingerprint(path)})
            previews = [f["path"] for f in catalog_files
                        if f.get("role") in ("preview", "render", "thumbnail")
                        and f.get("format", "").lower() in ("png", "jpg", "jpeg", "webp")]
        revision = digest(archive)
        record = {"id": record_id, "kind": "mesh", "name": str(catalog.get("asset_name") or "Asset")[:200],
                  "created": str(catalog.get("created_utc") or ""), "workflow": str(catalog.get('production',{}).get('workflow_title') or "Create a 3D Asset from an Image")[:120],
                  "variants": catalog.get("variants", []), "formats": sorted(set(f.get("format", "") for f in catalog_files)),
                  "warnings": catalog.get("warnings", []), "file_count": len(catalog_files),
                  "bytes": archive.stat().st_size, "archive": str(archive), "folder": str(folder),
                  "revision": revision, "preview_id": hashlib.sha256(previews[0].encode()).hexdigest()[:24] if previews else None,
                  "catalog": catalog}
        with self.lock, self.connect() as db:
            db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,0,?)",
                       (record_id, "mesh", record["created"], revision, json.dumps(record)))
            db.executemany("INSERT OR IGNORE INTO files VALUES(?,?,?,?)",
                           [(record_id, f["id"], f["path"], json.dumps(f)) for f in files])
        return self.public(record)

    def import_video(self, path, name, workflow, created):
        from .video_history import video_file

        path = owned_path(self.output_root, path)
        identity = fingerprint(path)
        if not video_file(path) or not identity or not identity["size"]:
            raise ValueError("Choose an existing Foundry video.")
        relative = path.relative_to(self.output_root).as_posix()
        record_id = hashlib.sha256(json.dumps(["video", relative.casefold(), identity], sort_keys=True).encode()).hexdigest()[:32]
        file = {"id": "video", "path": str(path), "name": path.name, "role": "video", "fingerprint": identity}
        record = {"id": record_id, "kind": "video", "name": str(name)[:200], "workflow": workflow,
                  "created": created, "formats": [path.suffix.lstrip(".").lower()], "variants": [], "warnings": [],
                  "file_count": 1, "filename": path.name, "bytes": identity["size"], "folder": str(path.parent),
                  "revision": str(identity["mtime"]), "preview_id": None, "catalog": {"files": []}}
        with self.lock, self.connect() as db:
            # A replay never revives a removed file. A regenerated file at a reused
            # name has a new identity, but an edited live record is left protected.
            live = db.execute("SELECT r.id FROM files f JOIN records r ON f.record_id=r.id "
                              "WHERE f.path=? AND r.removed=0", (str(path),)).fetchone()
            if live:
                return
            added = db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,0,?)",
                               (record_id, "video", created, record["revision"], json.dumps(record))).rowcount
            if added:
                db.execute("INSERT INTO files VALUES(?,?,?,?)",
                           (record_id, file["id"], str(path), json.dumps(file)))
        return self.public(record)

    def attach_front(self, record_id, source):
        """Keep a library-owned display copy; never acquire ownership of a source image."""
        from PIL import Image
        source=owned_path(self.output_root,source)
        if source.suffix.lower() not in (".png",".jpg",".jpeg",".webp") or source.stat().st_size>20*1024**2:
            raise ValueError("The front preview must be an image smaller than 20 MB.")
        with Image.open(source) as image:image.verify()
        with self.lock,self.connect() as db:
            record=self.record(record_id)
            if record.get("preview_id"):return
            target=owned_path(self.output_root,self.output_root/"foundry-previews"/(record_id+source.suffix.lower()))
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if digest(target)!=digest(source):raise ValueError("The existing library preview was edited; it has been preserved.")
            else:shutil.copyfile(source,target)
            item={"id":"front-preview","path":str(target),"name":target.name,"role":"thumbnail","fingerprint":fingerprint(target)}
            db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?)",(record_id,item["id"],str(target),json.dumps(item)))
            record["preview_id"]=item["id"]
            db.execute("UPDATE records SET data=? WHERE id=? AND removed=0",(json.dumps(record),record_id))

    @staticmethod
    def public(record, detail=False):
        keys = ("id", "kind", "name", "created", "workflow", "variants", "formats", "warnings",
                "file_count", "bytes", "preview_id")
        result = {k: record.get(k) for k in keys}
        if record["kind"] == "video": result["filename"] = record["filename"]
        if detail: result["catalog"] = record["catalog"]
        return result

    def record(self, record_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM records WHERE id=? AND removed=0", (record_id,)).fetchone()
        if not row: raise ValueError("This history entry is no longer available.")
        return json.loads(row["data"])

    def list(self, kind, cursor="", limit=24):
        self.kind(kind)
        if not isinstance(limit, int) or not 1 <= limit <= 24:
            raise ValueError("Request between 1 and 24 entries.")
        params = [kind]
        where = "kind=? AND removed=0"
        if cursor:
            with self.connect() as db:
                anchor = db.execute("SELECT created,id FROM records WHERE id=? AND kind=?", (cursor, kind)).fetchone()
            if not anchor: raise ValueError("The page cursor is no longer available.")
            where += " AND (created<? OR (created=? AND id<?))"
            params += [anchor["created"], anchor["created"], anchor["id"]]
        with self.connect() as db:
            rows = db.execute(f"SELECT data FROM records WHERE {where} ORDER BY created DESC,id DESC LIMIT ?",
                              (*params, limit + 1)).fetchall()
        items = [self.public(json.loads(r["data"])) for r in rows[:limit]]
        return {"items": items, "next_cursor": items[-1]["id"] if len(rows) > limit else None}

    def file(self, record_id, file_id):
        self.record(record_id)
        with self.connect() as db:
            row = db.execute("SELECT data FROM files WHERE record_id=? AND id=?", (record_id, file_id)).fetchone()
        if not row: raise ValueError("This file is not part of the selected export.")
        item = json.loads(row["data"])
        path = owned_path(self.output_root, item["path"])
        if not path.is_file(): raise ValueError("The saved file has moved or is no longer available.")
        if fingerprint(path) != item["fingerprint"]:
            raise ValueError("This saved file has changed since it was indexed.")
        return path

    def preview_removal(self, kind, record_ids=None, delete_files=False):
        self.kind(kind)
        if not isinstance(delete_files, bool): raise ValueError("Choose whether to delete saved files.")
        with self.lock, self.connect() as db:
            if record_ids is None:
                rows = db.execute("SELECT id FROM records WHERE kind=? AND removed=0 LIMIT 1001", (kind,)).fetchall()
                record_ids = [r["id"] for r in rows]
            if not isinstance(record_ids, list) or not record_ids or len(record_ids) > 1000:
                raise ValueError("Select between 1 and 1000 entries. Larger libraries can be cleared in batches.")
            record_ids = list(dict.fromkeys(record_ids))
            records = [self.record(i) for i in record_ids]
            if any(r["kind"] != kind for r in records): raise ValueError("The selection belongs to another library.")
            files = []
            if delete_files:
                for record in records:
                    for row in db.execute("SELECT data FROM files WHERE record_id=?", (record["id"],)):
                        item = json.loads(row["data"])
                        path = owned_path(self.output_root, item["path"])
                        if not path.exists(): continue
                        if fingerprint(path) != item["fingerprint"]:
                            raise ValueError("A saved file has changed. Remove the entry without deleting its files.")
                        shared = db.execute("SELECT f.record_id FROM files f JOIN records r ON f.record_id=r.id WHERE f.path=? AND r.removed=0",
                                            (str(path),)).fetchall()
                        if any(s["record_id"] not in record_ids for s in shared):
                            raise ValueError("A file is shared with an entry outside this selection.")
                        files.append({**item, "sha256": digest(path)})
            token = secrets.token_urlsafe(24)
            review = {"ids": record_ids, "revisions": {r["id"]: r["revision"] for r in records},
                      "kind": kind, "delete_files": delete_files, "files": files}
            db.execute("DELETE FROM reviews WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO reviews VALUES(?,?,?)", (token, time.time() + 600, json.dumps(review)))
        return {"token": token, "count": len(records), "names": [r["name"] for r in records],
                "delete_files": delete_files,
                "files": [str(Path(f["path"]).relative_to(self.output_root)) for f in files],
                "expires_in_seconds": 600}

    def remove(self, token):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT data,expires FROM reviews WHERE token=?", (token,)).fetchone()
            if not row or row["expires"] < time.time(): raise ValueError("This confirmation has expired. Review the selection again.")
            review = json.loads(row["data"])
            for record_id in review["ids"]:
                if self.record(record_id)["revision"] != review["revisions"][record_id]:
                    raise ValueError("The selected entry changed. Review it again.")
            if review["delete_files"]:
                if self.busy(): raise ValueError("Wait for current processing to finish before deleting saved files.")
                for item in review["files"]:
                    path = owned_path(self.output_root, item["path"])
                    if fingerprint(path) != item["fingerprint"] or digest(path) != item["sha256"]:
                        raise ValueError("A selected file changed. No files were deleted. Review the selection again.")
                    shared = db.execute("SELECT f.record_id FROM files f JOIN records r ON f.record_id=r.id WHERE f.path=? AND r.removed=0",
                                        (str(path),)).fetchall()
                    if any(s["record_id"] not in review["ids"] for s in shared):
                        raise ValueError("A selected file is now shared with another entry.")
                removed, failures = remove_exact([item["path"] for item in review["files"]])
                if failures:
                    return {"ok": False, "removed_files": len(removed), "failures": [str(Path(p).relative_to(self.output_root)) for p in failures],
                            "error": "Some files could not be deleted. History entries were retained."}
            db.executemany("UPDATE records SET removed=1 WHERE id=?", [(i,) for i in review["ids"]])
            db.execute("DELETE FROM reviews WHERE token=?", (token,))
        return {"ok": True, "removed_entries": len(review["ids"]), "deleted_files": len(review["files"])}
