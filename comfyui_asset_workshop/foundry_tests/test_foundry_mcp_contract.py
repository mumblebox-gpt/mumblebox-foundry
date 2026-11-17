"""Discovery, argument documentation, and side-effect hints from the real MCP SDK."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

if importlib.util.find_spec("mcp") is None:
    raise unittest.SkipTest("Run the tool contract tests in the dedicated Foundry MCP Python environment.")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from foundry_client import FoundryAPI
from foundry_server import create_server
from workspace import call, describe
from connection import AgentConnection, SESSION_HEADER


class FoundryMcpContractTests(unittest.IsolatedAsyncioTestCase):
    def test_rig_mutation_identity_does_not_depend_on_presence_notifications(self):
        client=FoundryAPI()
        connection=AgentConnection(client)
        self.assertEqual(client.headers.get(SESSION_HEADER),connection.session)
        self.assertEqual(client.upload_api.headers.get(SESSION_HEADER),connection.session)
        self.assertFalse(connection.initialized)

    async def test_hints_distinguish_catalogs_starts_and_mixed_dispatch(self):
        tools = {tool.name: tool for tool in await create_server(FoundryAPI()).list_tools()}
        self.assertTrue(tools["foundry_workflows"].annotations.read_only_hint)
        self.assertFalse(tools["foundry_start"].annotations.read_only_hint)
        self.assertTrue(tools["foundry_start"].annotations.open_world_hint)
        self.assertFalse(tools["foundry_workflow_action"].annotations.read_only_hint)
        self.assertTrue(tools["foundry_workflow_action"].annotations.destructive_hint)
        self.assertTrue(tools["foundry_image_remove"].annotations.destructive_hint)
        self.assertFalse(tools["foundry_image_removal_preview"].annotations.read_only_hint)
        self.assertFalse(tools["foundry_run_status"].annotations.read_only_hint)

    async def test_existing_arguments_stay_required_and_paths_gain_help(self):
        server = create_server(FoundryAPI())
        tools = {tool.name: tool for tool in await server.list_tools()}
        schema = tools["foundry_start"].input_schema
        self.assertEqual(set(schema["required"]), {"run_id", "operation", "request_id"})
        self.assertIn("Retry", schema["properties"]["request_id"]["description"])
        upload = tools["foundry_import_reference"].input_schema
        self.assertIn("authorized", upload["properties"]["path"]["description"])

    async def test_rigging_discovery_lists_live_view_and_revision_contract(self):
        tools = {tool.name: tool for tool in await create_server(FoundryAPI()).list_tools()}
        edit = tools["foundry_rig_edit"]
        self.assertTrue(tools["foundry_rig_view"].annotations.read_only_hint)
        self.assertFalse(edit.annotations.destructive_hint)
        self.assertIn("revision", edit.input_schema["required"])
        self.assertIn("step", edit.input_schema["properties"])
        self.assertIn("reset", edit.input_schema["properties"]["action"]["enum"])
        self.assertIn("bind_start", describe("rigging")["actions"])
        self.assertEqual(describe("rigging")["actions"]["bind_status"]["method"],"GET")
        self.assertEqual(describe("rigging")["actions"]["cancel_bind"]["method"],"POST")
        self.assertIn("foundry_rig_view", describe("rigging")["related_tools"])
        for name in ("foundry_rig_probe","foundry_rig_check"):
            self.assertTrue(tools[name].annotations.read_only_hint)
            self.assertIn(name,describe("rigging")["related_tools"])
        batch=tools["foundry_rig_batch"]
        self.assertFalse(batch.annotations.read_only_hint)
        self.assertEqual(set(batch.input_schema["required"]),{"run_id","rig_revision","request_id","operation"})
        self.assertIn("pose_joint",edit.input_schema["properties"]["action"]["enum"])

    def test_discovered_mesh_preparation_action_calls_only_shared_preview(self):
        facts = describe("mesh")["actions"]["preparation_preview"]
        self.assertEqual(facts["method"], "POST")
        self.assertIn("configuration", facts["body_fields"])
        client = FoundryAPI()
        client.request = Mock(return_value={"resources": []})
        body = {"configuration": {"method": "single-image"}, "operation": "mesh"}
        result = call(client, "mesh", "preparation_preview", body=body)
        self.assertEqual(result, {"resources": []})
        client.request.assert_called_once_with("/wizard/preparation-preview", body, method="POST")
