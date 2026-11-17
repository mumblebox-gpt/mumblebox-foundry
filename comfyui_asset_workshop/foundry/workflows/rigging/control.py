"""Persist the user's decision about agent editing independently of rig undo."""
import json
import time
from uuid import uuid4


class AgentEditingConflict(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AgentControl:
    def __init__(self, path, lock):
        self.path = path
        self.lock = lock
        self.resume_offer = None
        self.state = {"enabled": True, "epoch": 0, "changed_at": None, "reason": None}
        if path.exists():
            try:
                saved = json.loads(path.read_bytes())
                if type(saved["enabled"]) is not bool or type(saved["epoch"]) is not int or saved["epoch"] < 0:
                    raise ValueError("Invalid agent-control state.")
                self.state = saved
            except (ValueError, KeyError, TypeError):
                self.state.update(enabled=False, reason="unreadable_saved_state")

    def status(self):
        with self.lock:
            return dict(self.state)

    def stop(self, reason):
        with self.lock:
            return self._change(False, reason)

    def offer_resume(self, browser):
        with self.lock:
            capability = uuid4().hex
            self.resume_offer = (capability, browser, self.state["epoch"], time.monotonic() + 15)
            return capability

    def resume(self, ui_capability, browser):
        with self.lock:
            offer = self.resume_offer
            if (offer is None or offer[:3] != (ui_capability, browser, self.state["epoch"])
                    or offer[3] <= time.monotonic()):
                raise ValueError("Use Resume agent editing in the active Foundry wizard.")
            return self._change(True, "user_resumed")

    def check(self, context):
        if context is None or context["actor"] == "human":
            return
        with self.lock:
            if not self.state["enabled"]:
                raise AgentEditingConflict("stopped", "Agent editing is stopped. Only the user can resume it.")
            if context.get("control_epoch", self.state["epoch"]) != self.state["epoch"]:
                raise AgentEditingConflict("stale_control", "Agent editing changed while the operation was running.")

    def _change(self, enabled, reason):
        state = {"enabled": enabled, "epoch": self.state["epoch"] + 1,
                 "changed_at": time.time(), "reason": reason}
        partial = self.path.with_suffix(".tmp")
        partial.write_text(json.dumps(state), encoding="utf-8")
        partial.replace(self.path)
        self.state = state
        self.resume_offer = None
        return dict(state)
