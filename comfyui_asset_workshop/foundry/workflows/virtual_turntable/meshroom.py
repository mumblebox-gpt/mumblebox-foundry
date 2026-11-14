"""Meshroom is the sole owner of camera solving, dense reconstruction, UVs and texture projection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import folder_paths
from comfy_api.latest import Types
import comfy.model_management as mm
from .runtime import runtime_settings
from .references import CATEGORY

ROOT=Path(__file__).resolve().parent
from .processes import run_process, release_models
from .camera_validation import alicevision_centers, inspect_cameras, orbit_coverage

def runtime_environment(executable, cpu_threads):
    """Mirror Meshroom's Windows init script before launch, avoiding os.execv detachment."""
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(cpu_threads)
    if os.name == "nt":
        root = executable.parent
        # Official setupInitScriptWindows.py restarts itself unless this root is
        # already in ALICEVISION_LIBPATH. Pre-setting its exact environment keeps
        # the actual worker owned by our cancellable Popen, with its true exit code.
        native = [root / "aliceVision/bin", root / "aliceVision/lib", root / "lib", root]
        existing = [p for p in env.get("ALICEVISION_LIBPATH", "").split(os.pathsep) if p]
        env["ALICEVISION_LIBPATH"] = os.pathsep.join([str(p) for p in native] + existing)
        env["PYTHONPATH"] = os.pathsep.join([str(root / "aliceVision/lib/python"),
                                            str(root / "aliceVision/lib/python3.11/site-packages")])
    return env

class Reconstruct:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "frame_set":("V360_FRAMESET",),
            "depth_downscale":([1,2,4],{"default":1}),
            "depth_tile":("INT",{"default":768,"min":256,"max":2000,"step":32}),
            "neighbor_cameras":("INT",{"default":10,"min":2,"max":20}),
            "feature_density":(["normal","high","ultra"],),
            "min_2d_motion":("FLOAT",{"default":3.0,"min":0,"max":20,"step":0.5}),
            "initial_fov":("FLOAT",{"default":45.0,"min":10,"max":120,"step":1,"tooltip":"Starting horizontal field of view. Automatic calibration may refine it; Keep chosen lens holds it fixed. An assumption, not a measured H3 lens."}),
            "texture_size":([2048,4096,8192],{"default":4096}),
            "max_input_points":("INT",{"default":10000000,"min":1000000,"max":50000000,"step":1000000}),
            "max_mesh_points":("INT",{"default":1000000,"min":100000,"max":5000000,"step":100000}),
            "cpu_threads":("INT",{"default":8,"min":1,"max":64}),
            "timeout_minutes":("INT",{"default":180,"min":5,"max":1440}),
            "advanced_overrides":("STRING",{"default":"{}","multiline":True,"tooltip":"Optional native Meshroom node input overrides, e.g. {\"Texturing_1\":{\"unwrapMethod\":\"Basic\"}}. Consult the bundled native parameter guide."}),
        }, "optional": {
            "camera_calibration": (["Estimate lens automatically", "Keep chosen lens"], {
                "default": "Estimate lens automatically",
                "tooltip": "Keep chosen lens fixes the initial field of view, centered principal point and zero distortion during camera solving. Useful when generated views cause unstable lens estimates. The field of view is an assumption, not measured H3 camera data. Automatic estimates lens parameters from the images."
            }),
            "minimum_checked_fov": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 119, "step": 0.1, "tooltip": "Stop before dense depth when the solved horizontal FOV is below this experiment limit. Not a universal lens limit."}),
            "maximum_checked_fov": ("FLOAT", {"default": 120.0, "min": 1, "max": 179, "step": 1, "tooltip": "Stop before dense depth above this horizontal FOV. Passing checks does not prove reconstruction accuracy."}),
        }}
    RETURN_TYPES=("FILE_3D","STRING","STRING")
    RETURN_NAMES=("textured_glb","original_textured_obj","project_folder")
    FUNCTION="reconstruct"
    CATEGORY=CATEGORY
    def reconstruct(self,frame_set,depth_downscale,depth_tile,neighbor_cameras,feature_density,min_2d_motion,
                    initial_fov,texture_size,max_input_points,max_mesh_points,cpu_threads,timeout_minutes,advanced_overrides,camera_calibration=None,minimum_checked_fov=2.0,maximum_checked_fov=120.0):
        if not (0 < minimum_checked_fov < maximum_checked_fov < 180):
            raise ValueError("Camera check limits must satisfy 0 < minimum FOV < maximum FOV < 180.")
        runtime=runtime_settings()
        exe=Path(runtime["meshroom_batch"])
        if not exe.is_file():
            raise RuntimeError(f"Meshroom runtime is missing: {exe}")
        source=Path(frame_set["root"]).resolve()
        template=json.loads((ROOT/"object-turntable.mg").read_text(encoding="utf-8-sig"))
        graph=template["graph"]
        # Retain the official ObjectTurntable reconstruction chain. The existing
        # BiRefNet masks replace only the authors' prompt+SAM mask front end.
        del graph["ImageDetectionPrompt_1"]
        del graph["ImageSegmentationBox_1"]
        graph["FeatureExtraction_1"]["inputs"]["input"]="{CameraInit_1.output}"
        params={
            "CameraInit_1":{"defaultFieldOfView":initial_fov,"groupCameraFallback":"folder"},
            "FeatureExtraction_1":{"masksFolder":str(source/"masks"),"maskExtension":"png","maskInvert":False,
                                   "describerPreset":feature_density,"maxThreads":cpu_threads},
            "FeatureMatching_1":{"minRequired2DMotion":min_2d_motion},
            "PrepareDenseScene_1":{"masksFolders":[str(source/"masks")],"maskExtension":"png","outputFileType":"exr",
                                   "saveMatricesTxtFiles":True},
            "DepthMap_1":{"downscale":depth_downscale,"maxTCams":neighbor_cameras,
                          "tiling":{"tileBufferWidth":depth_tile,"tileBufferHeight":depth_tile,"tilePadding":64,"autoAdjustSmallImage":True}},
            "Meshing_1":{"maxInputPoints":max_input_points,"maxPoints":max_mesh_points},
            "Texturing_1":{"textureSide":texture_size,"downscale":1,"unwrapMethod":"Basic","outputMeshFileType":"obj","colorMapping":{"enable":True,"colorMappingFileType":"png"}},
        }
        extra=json.loads(advanced_overrides)
        if not isinstance(extra,dict):
            raise ValueError("Advanced overrides must be a JSON object keyed by native node name.")
        # Preserve path/mask contracts; other native controls remain available for deliberate tuning.
        reserved={"input","imagesFolder","imagesFolders","masksFolder","masksFolders","maskExtension","maskInvert",
                  "output","outputMeshFileType","inputFiles","viewpoints","intrinsics"}
        for name,values in extra.items():
            if name not in graph or not isinstance(values,dict):
                raise ValueError(f"Unknown native node or invalid overrides: {name}")
            if reserved.intersection(values):
                raise ValueError("Use the explicit graph inputs for paths, masks and output contracts.")
            params.setdefault(name,{}).update(values)
        # The named control owns calibration when supplied. Missing values retain
        # legacy graphs' advanced settings instead of silently changing their behavior.
        if camera_calibration is not None:
            if camera_calibration not in ("Estimate lens automatically", "Keep chosen lens"):
                raise ValueError("Choose automatic calibration or Keep chosen lens.")
            params.setdefault("StructureFromMotion_1", {})["lockAllIntrinsics"] = (
                camera_calibration == "Keep chosen lens")
        for name,values in params.items():
            graph[name].setdefault("inputs",{}).update(values)
        identity=json.dumps({"frames":frame_set["fingerprint"],"camera_checks":[minimum_checked_fov, maximum_checked_fov],"params":params,"runtime":runtime,"template":"ObjectTurntable / BiRefNet mask substitution","adapter":hashlib.sha256(Path(__file__).read_bytes() + (ROOT/"camera_validation.py").read_bytes()).hexdigest()},sort_keys=True)
        job=source/("meshroom-"+hashlib.sha256(identity.encode()).hexdigest()[:12])
        job.mkdir(exist_ok=True)
        pipeline=job/"pipeline.mg";project=job/"project.mg";output=job/"asset"
        pipeline.write_text(json.dumps(template,indent=2),encoding="utf-8")
        output.mkdir(exist_ok=True)
        log=job/"meshroom.log"
        command=[str(exe),"--pipeline",str(pipeline),"--input",str(source/"frames"),
                 "--output",str(output),"--save",str(project),
                 "--verbose","info"]
        # Omitting --cache lets --save establish the project filepath. With an
        # explicit cache, upstream setupProjectFile=False leaves it unset and
        # executeGraph.save() relocates the graph/cache to Windows Temp.
        env=runtime_environment(exe,cpu_threads)
        # No other application/process is touched. This releases only Comfy-managed models.
        release_models()
        if not __import__("torch").cuda.is_available():
            raise RuntimeError("AliceVision's dense-depth stage requires the configured NVIDIA CUDA GPU.")
        started=time.monotonic()
        # Let the official graph solve cameras first, then inspect the native
        # result before spending GPU time on depth. Reusing the same project and
        # cache resumes the official pipeline rather than reimplementing it.
        run_process(command + ["--toNode", "StructureFromMotion_1"],
                    exe.parent, env, log, timeout_minutes * 60)
        camera_files = list((job/"MeshroomCache/StructureFromMotion").glob("*/cameras.sfm"))
        if len(camera_files) != 1:
            raise RuntimeError(f"Expected one native camera solution, found {len(camera_files)}. Inspect {log}.")
        camera_data = json.loads(camera_files[0].read_text(encoding="utf-8-sig"))
        camera_check = inspect_cameras(camera_data,
                                       minimum_checked_fov, maximum_checked_fov)
        camera_check["native_camera_file"] = str(camera_files[0].relative_to(job))
        (job/"camera-validation.json").write_text(json.dumps(camera_check, indent=2), encoding="utf-8")
        if not camera_check["passed"]:
            raise RuntimeError("Camera validation stopped reconstruction before dense depth. "
                               + " ".join(camera_check["errors"])
                               + " Review the views and camera controls; Keep chosen lens uses the FOV you supply. "
                               + f"Details: {job/'camera-validation.json'}")
        remaining = timeout_minutes * 60 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Camera solving reached the selected total time limit; native cache is preserved.")
        run_process(command, exe.parent, env, log, remaining)
        obj=output/"texturedMesh.obj"
        if not obj.is_file() or obj.stat().st_size==0:
            raise RuntimeError(f"Meshroom did not publish the textured mesh. Inspect {log}.")
        import trimesh
        scene=trimesh.load(str(obj),force="scene",process=False)
        if not scene.geometry:
            raise RuntimeError("The published OBJ contains no geometry.")
        glb=output/"texturedMesh.glb"
        scene.export(str(glb),file_type="glb")
        faces=sum(len(g.faces) for g in scene.geometry.values())
        receipt={"elapsed_seconds":round(time.monotonic()-started,2),"faces":faces,"topology":"triangles",
                 "metric_scale":"unknown","watertight":"not guaranteed","camera_validation":camera_check,
                 "orbit_coverage":orbit_coverage(frame_set, alicevision_centers(camera_data)),
                 "original":str(obj),"preview":str(glb),"native_project":str(project),
                 "settings":params,"runtime":runtime,"template":"ObjectTurntable / BiRefNet mask substitution"}
        (job/"result.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        (job/"README.md").write_text(
            "# Virtual 360 Turntable output\n\n"
            "Experimental reconstruction from generated views. Inspect silhouettes, gaps, clay geometry and texture seams. "
            "A completed solve does not prove physical accuracy, watertightness, real scale or quad topology.\n\n"
            "- asset/texturedMesh.obj + MTL/PNG textures: original AliceVision textured triangle mesh. Keep these files together.\n"
            "- asset/texturedMesh.glb: packed preview/export conversion.\n"
            "- project.mg, MeshroomCache, meshroom.log: native project, reusable intermediates and process log.\n"
            "- result.json: settings, geometry counts and camera-check result.\n"
            "- camera-validation.json: numerical lens/pose checks performed before dense reconstruction. Passing does not prove accuracy or mesh quality.\n"
            "- ../frames.json, ../frames, ../masks: source frame indices, RGB and white-foreground masks.\n\n"
            "Credits: MiniMax H3, ComfyUI, BiRefNet, KJNodes and Meshroom/AliceVision. "
            "Their respective model/code licenses apply; see the standalone experiment README.\n",encoding="utf-8")
        return (Types.File3D(str(glb)),str(obj),str(job))
