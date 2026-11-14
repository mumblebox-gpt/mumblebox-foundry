from .references import ReferenceImage, MemoryProfile, SplitTurnaround, PrepareReferences, GuideFrames, VideoPrompt
from .frames import SelectFrames, SaveFrames, ResumeFrames, VideoSource, MaskFrames
from .meshroom import Reconstruct
from .colmap_openmvs import Reconstruct as ColmapOpenMVS
from .refinement import PrepareRefinement, RestoreRefinement, RefinementCheckpoint, ResumeRefinement
from .retexture import RetextureRefinement
from .colmap_finish import PrepareOpenMVSRefinement, TextureOpenMVSRefinement
from .colmap_export import ExportSettings, PresentGeometry
NODE_CLASS_MAPPINGS = {
    'FoundryV360OpenMVSExportSettings': ExportSettings,
    'FoundryV360PresentOpenMVSGeometry': PresentGeometry,
    'FoundryV360PrepareOpenMVSRefinement': PrepareOpenMVSRefinement,
    'FoundryV360TextureOpenMVSRefinement': TextureOpenMVSRefinement,
    'FoundryV360ResumeRefinement': ResumeRefinement,
    'FoundryV360PrepareRefinement': PrepareRefinement,
    'FoundryV360RestoreRefinement': RestoreRefinement,
    'FoundryV360RefinementCheckpoint': RefinementCheckpoint,
    'FoundryV360RetextureRefinement': RetextureRefinement,
    'FoundryV360ReferenceImage': ReferenceImage,
    'FoundryV360MemoryProfile': MemoryProfile,
    'FoundryV360SplitTurnaround': SplitTurnaround,
    'FoundryV360PrepareReferences': PrepareReferences,
    'FoundryV360GuideFrames': GuideFrames,
    'FoundryV360VideoPrompt': VideoPrompt,
    'FoundryV360SelectFrames': SelectFrames,
    'FoundryV360SaveFrames': SaveFrames,
    'FoundryV360ResumeFrames': ResumeFrames,
    'FoundryV360Meshroom': Reconstruct,
    'FoundryV360VideoSource': VideoSource,
    'FoundryV360MaskFrames': MaskFrames,
    'FoundryV360COLMAPOpenMVS': ColmapOpenMVS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    'FoundryV360ReferenceImage': 'Reference Image',
    'FoundryV360MemoryProfile': 'Virtual 360 - Memory and Size',
    'FoundryV360SplitTurnaround': 'Split Generated Four-View Sheet',
    'FoundryV360PrepareReferences': 'Prepare Four Generated Views - BiRefNet',
    'FoundryV360GuideFrames': 'Turnaround Guide Timing',
    'FoundryV360VideoPrompt': 'Orbit Prompt and Subject Direction',
    'FoundryV360SelectFrames': 'Select Reconstruction Frames',
    'FoundryV360SaveFrames': 'Save RGB and Foreground Masks',
    'FoundryV360ResumeFrames': 'Resume Saved Frame Set',
    'FoundryV360Meshroom': 'Meshroom - Cameras to Textured Mesh',
    'FoundryV360MaskFrames': 'BiRefNet - Bounded Frame Batches',
    'FoundryV360VideoSource': 'Branch Controls / Generated or Saved Video',
    'FoundryV360COLMAPOpenMVS': 'COLMAP + OpenMVS - Cameras to Textured Mesh',
}



class FrameReview:
    """Keep one durable contact sheet of the actual masked reconstruction frames."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "filename_prefix": ("STRING",)},
                "optional": {"frame_set": ("V360_FRAMESET",)}}

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "Foundry/Virtual Turntable"

    def save(self, images, filename_prefix, frame_set=None):
        import torch
        import torch.nn.functional as functional
        from nodes import SaveImage

        count = min(len(images), 16)
        indices = torch.linspace(0, len(images)-1, count).round().long().tolist()
        thumbs = functional.interpolate(images[indices].movedim(-1, 1), size=(160, 160),
                                        mode="bilinear", align_corners=False).movedim(1, -1)
        cols = min(count, 4)
        rows = []
        for index in range(0, count, cols):
            row = list(thumbs[index:index + cols])
            row += [torch.zeros_like(row[0])] * (cols - len(row))
            rows.append(torch.cat(row, dim=1))
        output = SaveImage().save_images(torch.cat(rows, dim=0).unsqueeze(0), filename_prefix)
        if frame_set:
            output["ui"]["text"] = [frame_set["root"]]
        return output


class ReconstructionResult:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("STRING", {"forceInput": True})}}

    RETURN_TYPES = ()
    FUNCTION = "receipt"
    OUTPUT_NODE = True
    CATEGORY = "Foundry/Virtual Turntable"

    def receipt(self, project):
        import json
        from pathlib import Path

        root = Path(project)
        payload = json.loads((root / "result.json").read_text(encoding="utf-8-sig"))
        payload["project"] = str(root)
        check = root / "camera-validation.json"
        if check.is_file():
            payload["camera_validation"] = json.loads(check.read_text(encoding="utf-8-sig"))
        return {"ui": {"text": [json.dumps(payload)]}}


from .refinement import ResumeRefinement


class RestoreSourceFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mesh": ("MESH",), "context": ("V360_REFINEMENT",)}}

    RETURN_TYPES = ("MESH",)
    FUNCTION = "restore"
    CATEGORY = "Foundry/Virtual Turntable"

    def restore(self, mesh, context):
        from .refinement import arrays, mesh_value
        from .refinement_geometry import restore_frame

        vertices, faces = arrays(mesh)
        return (mesh_value(restore_frame(vertices, context['transform']), faces),)


NODE_CLASS_MAPPINGS.update({
    "FoundryV360FrameReview": FrameReview,
    "FoundryV360ReconstructionResult": ReconstructionResult,
    "FoundryV360RestoreSourceFrame": RestoreSourceFrame,
    "FoundryV360ResumeRefinement": ResumeRefinement,
})
