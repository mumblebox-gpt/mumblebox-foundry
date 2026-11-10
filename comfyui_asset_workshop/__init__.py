from comfy_api.latest import ComfyExtension

from .nodes import AssetImage, LoadAssetImage, AssetMaster, LoadAssetMaster, AssetExport, PixalViewSet
from .nodes import ModelBudget, PrepareView, FinishPreparation, AssetScale, VerifiedModelLoRA
from .nodes import AssetDraft, LoadAssetDraft, AssetGuide, SourceFOV
from .nodes import SDXLCheckpoint, SDXLModelLoRA
from .pipeline_nodes import PIPELINE_NODES
from . import routes
from .foundry.routes import install as install_foundry_routes
install_foundry_routes()

WEB_DIRECTORY = "./web"


class AssetWorkshopExtension(ComfyExtension):
    async def get_node_list(self):
        return [AssetImage, LoadAssetImage, AssetMaster, LoadAssetMaster, AssetExport,
                PixalViewSet, ModelBudget, PrepareView, FinishPreparation, AssetScale, VerifiedModelLoRA,
                AssetDraft, LoadAssetDraft, AssetGuide, SourceFOV, SDXLCheckpoint, SDXLModelLoRA, *PIPELINE_NODES]


async def comfy_entrypoint():
    return AssetWorkshopExtension()

# Mixed V1/V3 registration: the node classes and IDs remain unchanged.
from .finishing.nodes import NODE_CLASS_MAPPINGS as FINISHING_NODES
from .finishing.nodes import NODE_DISPLAY_NAME_MAPPINGS
_NATIVE_NODES=[AssetImage, LoadAssetImage, AssetMaster, LoadAssetMaster, AssetExport,
    PixalViewSet, ModelBudget, PrepareView, FinishPreparation, AssetScale, VerifiedModelLoRA,
    AssetDraft, LoadAssetDraft, AssetGuide, SourceFOV, SDXLCheckpoint, SDXLModelLoRA, *PIPELINE_NODES]
NODE_CLASS_MAPPINGS={node.GET_SCHEMA().node_id:node for node in _NATIVE_NODES}
NODE_CLASS_MAPPINGS.update(FINISHING_NODES)
from .foundry.workflows.image_creation.nodes import NODE_CLASS_MAPPINGS as IMAGE_CREATION_NODES
NODE_CLASS_MAPPINGS.update(IMAGE_CREATION_NODES)
from .foundry.workflows.hair_creation.nodes import NODE_CLASS_MAPPINGS as HAIR_CREATION_NODES
NODE_CLASS_MAPPINGS.update(HAIR_CREATION_NODES)
from .foundry.workflows.splat_solid.nodes import NODE_CLASS_MAPPINGS as SPLAT_SOLID_NODES
NODE_CLASS_MAPPINGS.update(SPLAT_SOLID_NODES)
from .foundry.workflows.ccore_prop.nodes import NODE_CLASS_MAPPINGS as CCORE_NODES
NODE_CLASS_MAPPINGS.update(CCORE_NODES)
from .foundry.workflows.garment_particles.nodes import NODE_CLASS_MAPPINGS as GARMENT_NODES
NODE_CLASS_MAPPINGS.update(GARMENT_NODES)
from .foundry.workflows.guided_mesh.fvb.nodes import NODE_CLASS_MAPPINGS as GUIDED_NODES
NODE_CLASS_MAPPINGS.update(GUIDED_NODES)
from .foundry.workflows.guided_mesh.editor import NODES as GUIDED_EDITOR_NODES
NODE_CLASS_MAPPINGS.update(GUIDED_EDITOR_NODES)
