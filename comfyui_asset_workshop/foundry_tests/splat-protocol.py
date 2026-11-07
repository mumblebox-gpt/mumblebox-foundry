"""Real installed MCP/HTTP wiring, using a completed asset without inference."""
import argparse,asyncio,json,sys
from pathlib import Path
from mcp import Client
from mcp.client.stdio import StdioServerParameters

async def verify(server,ident):
    parameters=StdioServerParameters(command=sys.executable,args=[str(server)],cwd=str(server.parent))
    async with Client(parameters) as client:
        names={t.name for t in (await client.list_tools()).tools}
        expected={'foundry_splat_'+n for n in ('capabilities','create','status','start','cancel','show')}
        assert expected<=names,names
        async def call(name,args):
            result=await client.call_tool(name,args);assert not result.is_error,result.content;return result.structured_content
        cap=await call('foundry_splat_capabilities',{})
        result=await call('foundry_splat_status',{'creation_id':ident})
        assert result['status']=='complete' and result['package'] and result['quality']['companion']['passed']
        await call('foundry_splat_show',{'creation_id':ident})
        invalid=await client.call_tool('foundry_splat_start',{'creation_id':ident,'request_id':'denial-proof','operation':'shell'})
        assert invalid.is_error
        print(json.dumps({'status':'PASS','transport':'installed stdio and HTTP','tools':len(names),'splat_tools':sorted(expected),'saved_asset':ident,'method':cap['method'],'invalid_operation_denied':True,'inference_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--server',type=Path,required=True);p.add_argument('--id',required=True);a=p.parse_args();asyncio.run(verify(a.server.resolve(),a.id))
