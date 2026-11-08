"""Grounding has one geometry owner and never changes inference inputs."""
import json
from .grounding import plan_grounding
from .pipeline_nodes import vertices
class Hi3DGroundingFrame:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'mesh':('MESH',),'mode':(['level','place','original'],{'default':'level'})}}
    RETURN_TYPES=('STRING',);RETURN_NAMES=('grounding_plan',);FUNCTION='plan';CATEGORY='Hi3D/Finishing'
    def plan(self,mesh,mode):
        f=mesh.faces.detach().cpu().numpy()
        if f.ndim==3:f=f[0]
        return (json.dumps(plan_grounding(vertices(mesh),f,mode)),)
NODE_CLASS_MAPPINGS={'Hi3DGroundingFrame':Hi3DGroundingFrame}
NODE_DISPLAY_NAME_MAPPINGS={'Hi3DGroundingFrame':'Level support plane and place on floor'}
