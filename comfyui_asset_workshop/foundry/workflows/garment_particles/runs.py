"""Durable independent garment runs using the shared native Comfy queue."""
import asyncio
from heapq import nlargest
import json
from pathlib import Path
import time
from uuid import uuid4

from ...artifacts import owned_path
from ....store import atomic_json
from . import character, edits, runtime
from .contract import identifier, mesh_options, options
from .nodes import DRAPE, FIT, GENERATE, SEW, STAGE_NODE, directory
from .package import DRAPE_FILES, MESH_FILES, ORIGINALS, RIG_FILES, publish

ACTIVE = None


def busy():
    return bool(ACTIVE and ACTIVE.tasks)


class GarmentRuns:
    def __init__(self, state, output, native, lifecycle, library, other_busy):
        self.state, self.output = Path(state), Path(output).resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.native, self.lifecycle, self.library, self.other_busy = native, lifecycle, library, other_busy
        self.tasks, self.records = {}, {}

    def path(self, ident):
        return self.state / (identifier(ident) + ".json")

    def save(self, run):
        atomic_json(self.path(run["id"]), run)

    def get(self, ident):
        path = self.path(ident)
        if ident not in self.records:
            if not path.is_file():
                raise ValueError("This garment run could not be found.")
            run = json.loads(path.read_text(encoding="utf-8"))
            if run["status"] == "running":
                run.update(status="interrupted", error="ComfyUI stopped during this stage. Your earlier results remain saved.")
                self.save(run)
            self.records[ident] = run
        return self.records[ident]

    def public(self, run):
        ident = run["id"]
        phase = runtime.PHASE.get("text") if runtime.PHASE.get("job") == ident else None
        return {key: run.get(key) for key in ("id", "config", "status", "stage", "error", "result", "mesh", "rig",
                                               "started_at", "history_id", "drape", "edit", "parent")} | {
            "versions": self.versions(run),
            "active": ident in self.tasks, "phase": phase or run["phase"], "archive": bool(run.get("archive")),
        }

    def versions(self, run):
        root = self.get(edits.root_id(run))
        ids = [root["id"], *root.get("children", [])]
        return [{"id": child["id"], "parent": child.get("parent"), "edit": child.get("edit"),
                 "seed": child["config"]["seed"], "name": child["config"]["name"]}
                for child in (self.get(ident) for ident in ids) if child["result"]]

    def mix_sources(self, ident):
        root = edits.root_id(self.get(ident))
        sources = {}
        paths = nlargest(48, self.state.glob('*.json'), key=lambda path: path.stat().st_mtime_ns)
        for path in paths:
            try:
                run = json.loads(path.read_text(encoding='utf-8'))
                design = edits.root_id(run)
                if not run['result'] or design == root or design in sources:
                    continue
                config = run['config']
                sources[design] = {key: config[key] for key in ('name', 'seed')} | {'id': run['id']}
            except (OSError, KeyError, ValueError):
                continue
            if len(sources) == 16:
                break
        return list(sources.values())

    def edit(self, ident, data):
        source = self.get(ident)
        if not source["result"]:
            raise ValueError("Generate and review a garment before editing it.")
        self.check_available()
        job = identifier(data.get("request_id"))
        if self.path(job).exists():
            raise ValueError("This edit request is already saved.")
        root = self.get(edits.root_id(source))
        if len(root.get("children", [])) >= 64:
            raise ValueError("This garment has 64 saved revisions. Start a fresh design to continue.")
        controls = edits.edit_options(data.get("edit"))
        config = edits.edit_generation(data, source["config"])
        run = dict(id=job, config=config, result=None, mesh=None, drape=None, rig=None,
                   root=root["id"], parent=ident, edit=controls["operation"])
        self.records[job] = run
        return self.launch(run, "edit", GENERATE,
                           {**config, "job": job, "edit": json.dumps(controls, separators=(",", ":"))}, data)

    def guide(self, ident):
        import numpy as np

        path = self.file(ident, "particles.npz")
        with np.load(path, allow_pickle=False) as stored:
            points = stored["particles"]
        if points.ndim != 2 or points.shape[1] != 6 or len(points) > 8192 or not np.isfinite(points).all():
            raise ValueError("The saved particle data is invalid.")
        if len(points) > 4096:
            points = points[np.linspace(0, len(points) - 1, 4096, dtype=int)]
        return {"points": np.around(points, 3).tolist()}

    def check_available(self):
        if self.tasks or self.native.active_ids() or self.other_busy():
            raise ValueError("Wait for the current Foundry workflow to finish before running a garment stage.")

    def start(self, data):
        ident = identifier(data.get("request_id"))
        config = options(data)
        if self.path(ident).exists():
            run = self.get(ident)
            if run["config"] != config:
                raise ValueError("This garment request belongs to different inputs.")
            return self.public(run)
        self.check_available()
        warning = runtime.availability()[config["mode"]]
        if warning:
            raise ValueError(warning)
        run = dict(id=ident, config=config, result=None, mesh=None, rig=None)
        self.records[ident] = run
        return self.launch(run, "generate", GENERATE, {**config, "job": ident}, data)

    def sew(self, ident, data):
        run = self.get(ident)
        if not run["result"]:
            raise ValueError("Generate and review the sewing pattern first.")
        self.check_available()
        return self.launch(run, "sew", SEW, {"garment_run": ident, **mesh_options(data)}, data)

    def drape(self, ident, data):
        run = self.get(ident)
        if not run["mesh"]:
            raise ValueError("Build a sewn garment mesh before draping.")
        self.check_available()
        controls = character.drape_options(data)
        if not character.path(directory(self.output, ident), controls["character"]).is_file():
            raise ValueError("Upload a rigged character GLB before draping.")
        token = ident + "/" + run["mesh"]["mesh_id"]
        return self.launch(run, "drape", DRAPE, {"mesh_token": token, **controls}, data)

    def fit(self, ident, data):
        run = self.get(ident)
        drape = run.get("drape")
        if not drape or drape["mesh_id"] != (run.get("mesh") or {}).get("mesh_id") or data.get("approve") != drape["drape_id"]:
            raise ValueError("Review and approve the current drape before transferring skin weights.")
        self.check_available()
        return self.launch(run, "fit", FIT, {"mesh_token": ident + "/" + drape["drape_id"]}, data)

    def package(self, ident):
        run = self.get(ident)
        if not run["result"]:
            raise ValueError("Generate and review the garment first.")
        if run.get("archive"):
            return self.public(run)
        self.check_available()
        return self.launch(run, "package", None, {}, {})

    def launch(self, run, stage, node, inputs, data):
        labels = {"generate": "Preparing Garment Particles", "sew": "Preparing the sewing pattern",
                  "edit": "Preparing the author-guided edit", "drape": "Preparing cloth simulation",
                  "package": "Saving the garment package", "fit": "Transferring skin weights"}
        run.update(stage=stage, status="running", phase=labels[stage], error="", started_at=time.time(),
                   prompt_id=str(uuid4()) if node else None, cancelled=False)
        if node:
            run["native_graph"] = {STAGE_NODE: {"class_type": node, "inputs": inputs}}
        self.save(run)
        self.tasks[run["id"]] = asyncio.create_task(self.execute(run, node, inputs, str(data.get("client_id", ""))[:100]))
        return self.public(run)

    def cancel(self, ident):
        run = self.get(ident)
        if ident in self.tasks:
            run["cancelled"] = True
            if run["prompt_id"]:
                self.native.cancel(run["prompt_id"])
            self.save(run)
        return self.public(run)

    @staticmethod
    def check(run):
        if run["cancelled"]:
            raise InterruptedError("This stage was stopped. Your earlier results remain saved.")

    async def execute(self, run, node, inputs, client_id):
        ident, prompt_id = run["id"], run["prompt_id"]
        try:
            if node:
                await self.lifecycle().barrier()
                if node == GENERATE:
                    await self.lifecycle().release("before Garment Particles generation")
                self.check(run)
                await self.native.submit(run["native_graph"], prompt_id, client_id)
                if run["cancelled"]:
                    self.native.cancel(prompt_id)
                history = await self.native.wait(prompt_id, 1830, lambda: run["cancelled"])
                self.check(run)
                status = history.get("status", {})
                if status.get("status_str") != "success":
                    messages = [data.get("exception_message") for event, data in status.get("messages", [])
                                if event == "execution_error" and data.get("exception_message")]
                    raise ValueError(messages[-1] if messages else "The Comfy garment stage did not finish.")
                receipt = history["outputs"][STAGE_NODE]["garment"][0]
                if node == GENERATE:
                    run.update(result=receipt, phase="Sewing pattern ready")
                    if run.get("parent"):
                        root = self.get(edits.root_id(run))
                        root.setdefault("children", []).append(ident)
                        self.save(root)
                elif node == SEW:
                    run.update(mesh=receipt, drape=None, rig=None, archive=None, history_id=None, phase="Sewn polygon mesh ready")
                elif node == DRAPE:
                    run.update(drape=receipt, rig=None, archive=None, history_id=None, phase="Settled cloth ready for review")
                else:
                    run.update(rig=receipt, archive=None, history_id=None, phase="Character fit ready for review")
            else:
                source = directory(self.output, ident)
                mesh = source / "Mesh" / identifier(run["mesh"]["mesh_id"]) if run["mesh"] else None
                rig = source / "Fit" / identifier(run["rig"]["fit_id"]) if run["rig"] else None
                drape = source / "Drape" / identifier(run["drape"]["drape_id"]) if run.get("drape") else None
                archive, record = await asyncio.to_thread(publish, run, source, mesh, rig, self.library,
                                                          lambda: self.check(run), drape=drape)
                run.update(archive=archive.relative_to(self.output).as_posix(), history_id=record, phase="Garment package saved")
            run["status"] = "complete"
        except InterruptedError as error:
            run.update(status="cancelled", error=str(error))
        except Exception as error:
            run.update(status="failed", error=str(error)[:1600] or "The garment stage could not finish.")
        finally:
            self.tasks.pop(ident, None)
            self.save(run)

    def file(self, ident, name):
        run = self.get(ident)
        source = directory(self.output, ident)
        if name == "archive" and run.get("archive"):
            path = self.output / run["archive"]
        elif name in ORIGINALS and run["result"]:
            path = source / name
        elif name in MESH_FILES and run["mesh"]:
            path = source / "Mesh" / identifier(run["mesh"]["mesh_id"]) / name
        elif name in DRAPE_FILES and run.get("drape"):
            path = source / "Drape" / identifier(run["drape"]["drape_id"]) / name
        elif name in RIG_FILES and run["rig"]:
            path = source / "Fit" / identifier(run["rig"]["fit_id"]) / name
        else:
            raise ValueError("This garment output is not available.")
        path = owned_path(self.output, path)
        if not path.is_file():
            raise ValueError("The garment output file was moved or removed.")
        return path

