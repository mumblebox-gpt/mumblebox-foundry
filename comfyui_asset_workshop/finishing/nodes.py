"""Registration owner for the shipped Hi3D/finishing adapters."""
from ..pipeline_workers.refine_client import Hi3DBackend, Hi3DLoadMesh, Hi3DRefine
from . import pipeline_nodes, trellis_nodes, optimization_nodes, finishing_nodes, quad_nodes, grounding_nodes
NODE_CLASS_MAPPINGS={c.__name__:c for c in (Hi3DBackend,Hi3DLoadMesh,Hi3DRefine)}
NODE_DISPLAY_NAME_MAPPINGS={}
for module in (pipeline_nodes,trellis_nodes,optimization_nodes,finishing_nodes,quad_nodes,grounding_nodes):
    NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)
