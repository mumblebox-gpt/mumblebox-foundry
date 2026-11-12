"""Setup metadata and local presence stay tied to the running installation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.agent_connection import AgentPresence, installation


class AgentConnectionTests(unittest.TestCase):
    def test_comfy_prompt_has_real_launch_details(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"MUMBLEBOX_PINOKIO_ROOT": ""}):
            setup = installation(8188, folder, None)
            entry = setup["configuration"]["mcpServers"]["mumblebox-foundry"]
            self.assertTrue(Path(setup["skill_path"]).is_file())
            self.assertTrue(Path(entry["args"][0]).is_file())
            self.assertEqual(entry["args"][1:], ["--comfy-url", "http://127.0.0.1:8188"])
            self.assertTrue(Path(entry["command"]).is_relative_to(Path(folder).resolve()))
            self.assertTrue(Path(setup["install_python"]["requirements"]).is_file())

    def test_pinokio_reuses_the_launcher_owned_configuration(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"MUMBLEBOX_PINOKIO_ROOT": folder}):
            state = Path(folder) / ".pinokio"
            state.mkdir()
            expected = {"mcpServers": {"mumblebox-foundry": {"command": "actual-python", "args": ["actual-wrapper"]}}}
            (state / "mcp.json").write_text(json.dumps(expected), encoding="utf-8")
            setup = installation(27184, folder, None)
            self.assertEqual(setup["configuration"], expected)
            self.assertEqual(setup["install_directory"], folder)
            self.assertIsNone(setup["install_python"])

    def test_presence_expires_connections_without_losing_running_agent_jobs(self):
        now = 0
        active = True
        presence = AgentPresence(clock=lambda: now, active=lambda *_: active)
        session = "a" * 32
        self.assertTrue(presence.observe(session, 0, False))
        self.assertFalse(presence.snapshot()["working"])
        self.assertFalse(presence.observe(session, 1, True))
        self.assertTrue(presence.snapshot()["working"])
        presence.track(session, "/mumblebox-foundry/v1/virtual-turntable/runs/id/start",
                       {"active": True, "id": "b" * 32})
        now = 46
        self.assertEqual(presence.snapshot()["connected"], 0)
        self.assertEqual(presence.snapshot()["running_jobs"], 1)
        active = False
        self.assertFalse(presence.snapshot()["working"])


if __name__ == "__main__":
    unittest.main()
