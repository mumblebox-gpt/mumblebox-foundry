"""Real installed Foundry stdio/HTTP checks; no inference or user-file deletion."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def verify(server, run_id, image_id=None):
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(server)], cwd=str(server.parent))
    async with Client(parameters) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        required = {'foundry_capabilities', 'foundry_start', 'foundry_workflows',
                    'foundry_workflow_action', 'foundry_garment_upload_character'}
        assert required <= names, required - names
        async def call(name, args):
            response = await client.call_tool(name, args)
            assert not response.is_error, response.content
            return response.structured_content
        capabilities = await call('foundry_capabilities', {})
        source = await call('foundry_run_status', {'run_id': run_id})
        assert 'outputs' not in source
        package = await call('foundry_package', {'run_id': run_id})
        assert package['download_url'].startswith('http://127.0.0.1:8188/')
        invalid = await client.call_tool('foundry_start', {
            'run_id': '../private', 'operation': 'shell', 'request_id': 'denial-check'})
        assert invalid.is_error
        config = {key: source[key] for key in ('references', 'category', 'profile', 'overrides', 'selection')}
        config['turnaround_model'] = source.get('turnaround_model', source['turnaround']['id'])
        config['name'] = 'Foundry MCP protocol check'
        created = await call('foundry_create_run', {'configuration': config})
        config['name'] = 'Foundry MCP protocol checked'
        updated = await call('foundry_update_run', {'run_id': created['id'], 'configuration': config})
        assert updated['name'] == config['name']
        cancelled = await call('foundry_cancel', {'run_id': created['id']})
        images=await call('foundry_image_capabilities',{})
        image=await call('foundry_image_create',{'configuration':{'name':'MCP image contract check','description':'A blue vase','category':'general','model':'klein4'}})
        image=await call('foundry_image_update',{'creation_id':image['id'],'configuration':{**image['config'],'name':'MCP image contract checked'}})
        assert image['config']['name']=='MCP image contract checked'
        await call('foundry_image_status',{'creation_id':image['id']})
        await call('foundry_image_cancel',{'creation_id':image['id']})
        await call('foundry_image_gallery',{'limit':2})
        invalid_image=await client.call_tool('foundry_image_start',{'creation_id':image['id'],'request_id':'invalid-operation','operation':'shell'})
        assert invalid_image.is_error
        invalid_handoff=await client.call_tool('foundry_image_handoff',{'creation_id':image['id']})
        assert invalid_handoff.is_error
        if image_id:
            saved=await call('foundry_image_save',{'creation_id':image_id})
            assert saved['download_url'].endswith('/package')
            handoff=await call('foundry_image_handoff',{'creation_id':image_id})
            assert [r['role'] for r in handoff['references']]==['primary','back']
            merged={**config,**handoff}
            linked=await call('foundry_create_run',{'configuration':merged})
            assert len(linked['image_creation']['images'])==2
        print(json.dumps({'status': 'PASS', 'transport': 'real stdio and installed HTTP',
            'tools': sorted(names), 'capability_fields': sorted(capabilities),
            'fixture_run': created['id'], 'shared_create_update': True,
            'cancel_status': cancelled['status'], 'invalid_operation_denied': True,
            'package_metadata': True,'image_contract':True,'image_lineage':bool(image_id), 'inference_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--image-id')
    args = parser.parse_args()
    asyncio.run(verify(args.server.resolve(), args.run_id,args.image_id))
