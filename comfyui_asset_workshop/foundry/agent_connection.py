"""Local MCP presence and installation details for Foundry's setup dialog."""
import asyncio
from importlib import import_module
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import time

from . import VERSION

SESSION_HEADER = "X-Foundry-Agent-Session"
SESSION_ID = re.compile(r"[0-9a-f]{32}")
PACKAGE = Path(__file__).resolve().parents[1]
SKILL = PACKAGE / "skills" / "mumblebox-assets"
WORKFLOWS = {
    "wizard": "image_to_3d", "guided": "guided_mesh", "splat": "splat_solid",
    "hair": "hair_creation", "ccore": "ccore_prop", "garment": "garment_particles",
    "images": "image_creation", "virtual-turntable": "virtual_turntable", "orbit-to-mesh": "orbit_to_mesh",
}


def local_request(request):
    try:
        address = ipaddress.ip_address(request.remote or "")
        return (getattr(address, "ipv4_mapped", None) or address).is_loopback
    except ValueError:
        return False


def bundled_skill():
    return json.loads((SKILL / "compatibility.json").read_text(encoding="utf-8"))


def connection_details():
    return {"version": VERSION, "skill_path": str(SKILL / "SKILL.md"), "skill": bundled_skill()}


def installation(port, user_directory, blender):
    address = f"http://127.0.0.1:{port}"
    pinokio = os.environ.get("MUMBLEBOX_PINOKIO_ROOT")
    if pinokio:
        root = Path(pinokio)
        configuration = json.loads((root / ".pinokio" / "mcp.json").read_text(encoding="utf-8"))
        entry = configuration["mcpServers"]["mumblebox-foundry"]
        install_python = None
    else:
        root = PACKAGE
        environment = Path(user_directory).resolve() / "mumblebox-foundry" / "agent-env"
        executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        entry = {"command": str(executable), "args": [str(PACKAGE / "agent" / "foundry_server.py"), "--comfy-url", address]}
        install_python = {
            "base_python": sys.executable, "environment": str(environment),
            "requirements": str(PACKAGE / "agent" / "requirements.txt"),
        }
    return {
        **connection_details(), "install_directory": str(root), "address": address,
        "configuration": {"mcpServers": {"mumblebox-foundry": entry}},
        "install_python": install_python,
        "blender": str(blender) if blender and Path(blender).is_file() else None,
    }


def job_active(group, ident):
    owner = import_module(f"{__package__}.workflows.{WORKFLOWS[group]}.runs").ACTIVE
    if owner is None:
        return False
    if ident in owner.tasks:
        return True
    if group == "guided":
        if ident in owner.engine.runner.active:
            return True
        if owner.finisher.tasks:
            return owner.get(ident).get("export_run_id") in owner.finisher.tasks
    return False


class AgentPresence:
    """Small in-memory leases. The workflow owners remain authoritative for jobs."""

    def __init__(self, clock=time.monotonic, active=job_active):
        self.clock = clock
        self.active = active
        self.sessions = {}
        self.jobs = set()
        self.last_used = None
        self.last_used_at = None
        self.update_task = None
        self.update_result = None

    def expire(self):
        now = self.clock()
        for ident, (_, seen) in list(self.sessions.items()):
            if now - seen > 45:
                self.sessions.pop(ident)

    def observe(self, ident, calls, used):
        self.expire()
        fresh = ident not in self.sessions
        if fresh and len(self.sessions) >= 32:
            raise ValueError("Too many local agent connections.")
        now = self.clock()
        self.sessions[ident] = calls, now
        if used:
            self.last_used = now
            self.last_used_at = time.time()
        return fresh

    def track(self, session, path, result):
        if session not in self.sessions or not isinstance(result, dict) or result.get("active") is not True:
            return
        group = path.split("/", 4)[3]
        ident = result.get("id")
        if group in WORKFLOWS and isinstance(ident, str) and SESSION_ID.fullmatch(ident):
            self.jobs.add((group, ident))

    def snapshot(self):
        self.expire()
        self.jobs = {job for job in self.jobs if self.active(*job)}
        recent = self.last_used is not None and self.clock() - self.last_used < 3
        return {"connected": len(self.sessions), "running_jobs": len(self.jobs),
                "working": bool(self.jobs or (self.sessions and recent) or any(n for n, _ in self.sessions.values())),
                "last_used_at": self.last_used_at}

    async def check_updates(self, updates):
        self.update_result = await asyncio.to_thread(updates.check)

    def check_on_connect(self, updates):
        if updates and (self.update_task is None or self.update_task.done()):
            self.update_task = asyncio.create_task(self.check_updates(updates))

    def versions(self, updates):
        status = updates.status() if updates else {"state": "unavailable"}
        if self.update_result and self.update_result.get("state") == "disabled":
            if not updates.preferences.read()["auto_check_updates"]:
                status = self.update_result
        return {**connection_details(), "update": status,
                "checking": self.update_task is not None and not self.update_task.done()}


PRESENCE = AgentPresence()
