"""Safe native checkpoint loading; generation remains in the original native nodes."""
from pathlib import Path
from ...artifacts import owned_path

class FoundrySplatLoadMesh:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'filename':('STRING',{'default':''})}}
    RETURN_TYPES=('MESH',)
    FUNCTION='load'
    CATEGORY='Foundry/Splat & Solid'
    def load(self,filename):
        import folder_paths,torch,trimesh
        import numpy as np
        from comfy_api.latest import Types
        root=folder_paths.get_output_directory()
        path=owned_path(root,Path(root)/filename)
        if path.suffix.lower()!='.glb' or not path.is_file():raise ValueError('A saved GLB checkpoint is required.')
        mesh=trimesh.load(path,force='mesh',process=False)
        if len(mesh.faces)>10000000 or not np.isfinite(mesh.vertices).all():raise ValueError('Checkpoint geometry exceeds the supported bounds.')
        return (Types.MESH(vertices=torch.from_numpy(np.asarray(mesh.vertices,dtype=np.float32).copy()).unsqueeze(0),faces=torch.from_numpy(np.asarray(mesh.faces,dtype=np.int64).copy()).unsqueeze(0)),)

NODE_CLASS_MAPPINGS={'FoundrySplatLoadMesh':FoundrySplatLoadMesh}
