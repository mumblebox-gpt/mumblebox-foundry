"""Durable wizard runs with one native Comfy job per generation."""
import asyncio
import json
from pathlib import Path
import re
import time
import uuid

from ...artifacts import owned_path
from ....store import atomic_json
from .contract import STANDARD_MODEL, options
from .generation import STATE
from .nodes import PROMPT_NODE, graph

ACTIVE = None


def busy():
    return ACTIVE is not None and bool(ACTIVE.tasks or ACTIVE.enhancement)


class PropRuns:
    def __init__(self, state, output, native, lifecycle, library, other_busy):
        self.state, self.output = Path(state), Path(output).resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.native, self.lifecycle, self.library, self.other_busy = native, lifecycle, library, other_busy
        self.tasks, self.records = {}, {}
        self.enhancement = None

    def path(self, ident):
        if not isinstance(ident, str) or not re.fullmatch("[a-f0-9]{32}", ident):
            raise ValueError("Invalid CCORE prop run.")
        return self.state / (ident + ".json")

    def save(self, run):
        atomic_json(self.path(run["id"]), run)

    def get(self, ident):
        path = self.path(ident)
        if ident not in self.records:
            if not path.is_file():
                raise ValueError("This CCORE prop run is no longer available.")
            run = json.loads(path.read_text(encoding="utf-8"))
            run["config"].setdefault("model_variant", STANDARD_MODEL)
            if run["status"] == "running":
                run.update(status="interrupted", error="Generation was interrupted. Start a new attempt.")
                self.save(run)
            self.records[ident] = run
        return self.records[ident]

    def public(self, run):
        from .... import models

        ident = run["id"]
        active = ident in self.tasks
        progress = STATE.get("phase") if STATE.get("job") == ident else None
        download = models.DOWNLOAD
        transfer = None
        if download.get("owner") == ident and download.get("status") == "running":
            transfer = {key: download.get(key) for key in ("name", "bytes", "total", "phase")}
        return {key: run[key] for key in ("id", "config", "status", "error", "result")} | {
            "active": active, "phase": progress or run["phase"], "download": transfer,
            "started_at": run.get("started_at"),
            "smaller_budget": run.get("smaller_budget"),
            "fallbacks": run.get("fallbacks", []),
        }

    def start(self, data):
        ident = data.get("request_id")
        path = self.path(ident)
        config = options(data)
        if path.exists():
            run = self.get(ident)
            if run["config"] != config:
                raise ValueError("This generation request belongs to another description.")
            return self.public(run)
        if self.tasks or self.enhancement or self.native.active_ids() or self.other_busy():
            raise ValueError("Wait for the current Foundry workflow to finish before generating a prop.")
        run = dict(id=ident, config=config, status="running", phase="Preparing CCORE",
                   error="", result=None, prompt_id=str(uuid.uuid4()), cancelled=False, started_at=time.time())
        self.save(run)
        self.records[ident] = run
        self.tasks[ident] = asyncio.create_task(self.execute(run, str(data.get("client_id", ""))[:100]))
        return self.public(run)

    async def enhance(self, ident, prompt, operation="enhance", precision=None):
        from .... import description_helper
        from .enhancement import write_description

        if operation not in ("enhance", "translate"):
            raise ValueError("Choose enhancement or translation.")
        if self.tasks or self.enhancement or self.native.active_ids() or self.other_busy():
            raise ValueError("Wait for the current Foundry workflow to finish before enhancing.")
        description_helper.claim(ident)
        self.enhancement = ident
        try:
            await self.lifecycle().barrier()
            await self.lifecycle().release("before CCORE description " + operation)
            description_helper.check_cancelled()
            task = asyncio.create_task(asyncio.to_thread(write_description, ident, prompt, operation, precision))
            try:
                text = await asyncio.shield(task)
            except asyncio.CancelledError:
                description_helper.cancel(ident)
                await asyncio.gather(task, return_exceptions=True)
                raise
            description_helper.check_cancelled()
            return {"text": text, "cancelled": False}
        except (InterruptedError, OSError, ValueError):
            if description_helper.STATE.get("cancel"):
                return {"cancelled": True}
            raise
        finally:
            self.enhancement = None
            description_helper.release()

    def cancel_enhancement(self, ident):
        from .... import description_helper

        if self.enhancement == ident:
            description_helper.cancel(ident)
        return {"cancelled": self.enhancement == ident}

    def cancel(self, ident):
        run = self.get(ident)
        if ident in self.tasks and run["phase"] != "Saving prop and package":
            from .... import models

            run["cancelled"] = True
            if models.DOWNLOAD.get("owner") == ident:
                models.DOWNLOAD["cancel"] = True
            self.native.cancel(run["prompt_id"])
            self.save(run)
        return self.public(run)

    @staticmethod
    def check(run):
        if run["cancelled"]:
            raise InterruptedError("Generation stopped. You can try the description again.")

    async def execute(self, run, client_id):
        from .package import publish

        ident = run["id"]
        prompt_id = run["prompt_id"]
        try:
            await self.lifecycle().barrier()
            await self.lifecycle().release("before CCORE prop generation")
            self.check(run)
            await self.native.submit(graph(run["config"], ident), prompt_id, client_id)
            if run["cancelled"]:
                self.native.cancel(prompt_id)
            history = await self.native.wait(prompt_id, 7200, lambda: run["cancelled"])
            self.check(run)
            status = history.get("status", {})
            if status.get("status_str") != "success":
                errors = [data.get("exception_message") for event, data in status.get("messages", [])
                          if event == "execution_error" and data.get("exception_message")]
                raise ValueError(errors[-1] if errors else "The CCORE stage was interrupted.")
            item = history["outputs"][PROMPT_NODE]["ccore"][0]
            if item.get("error"):
                run.update(status="failed", phase="GPU memory check", error=item["error"],
                           smaller_budget=item["smaller_budget"], fallbacks=item["fallbacks"])
                return
            model = owned_path(self.output, self.output / item["subfolder"] / item["filename"])
            if item.get("prepared_reference_sha256"):
                run["prepared_reference_sha256"] = item["prepared_reference_sha256"]
            run.update(phase="Saving prop and package")
            self.save(run)
            archive, history_id = await asyncio.to_thread(
                publish, model, item["measurements"], run, self.library, lambda: self.check(run)
            )
            run.update(status="complete", phase="Prop ready",
                       result={"model": model.relative_to(self.output).as_posix(),
                               "archive": archive.relative_to(self.output).as_posix(),
                               "history_id": history_id, "measurements": item["measurements"]})
        except InterruptedError as error:
            run.update(status="cancelled", error=str(error))
        except Exception as error:
            run.update(status="failed", error=str(error)[:2400] or "CCORE could not finish this prop.")
        finally:
            self.tasks.pop(ident, None)
            self.save(run)

    def file(self, ident, kind):
        result = self.get(ident)["result"]
        if not result or kind not in ("model", "archive"):
            raise ValueError("This prop has no saved file of that kind.")
        path = owned_path(self.output, self.output / result[kind])
        if not path.is_file():
            raise ValueError("The saved file is no longer available.")
        return path
