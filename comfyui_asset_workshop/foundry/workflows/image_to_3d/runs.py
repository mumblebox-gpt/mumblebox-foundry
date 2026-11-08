"""Durable, bounded execution of the image-to-3D wizard.

This owner persists immutable stage requests and completed file checkpoints. It
uses Comfy's existing queue and resource lifecycle; it never owns model tensors.
"""
import asyncio
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from .definition import DEFAULT_SELECTION, VERSION, resolve_settings
from .prompts import bind_references
from .graph import compile_stage, STAGE_KEYS, DEPENDENCIES
from .turnaround import model_spec
from .progress import snapshot as progress_snapshot
from ...artifacts import digest, owned_path

ACTIVE = None

def busy():
    return ACTIVE is not None and bool(ACTIVE.tasks)

def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def output_entry(outputs, node, kind):
    items = outputs.get(str(node),{}).get(kind,[])
    if not items or not isinstance(items[0],dict):
        raise ValueError("The stage completed without its required saved output: "+str(node))
    return items[0]

def view_url(entry):
    return "/view?" + urlencode({k:entry[k] for k in ("filename","subfolder","type")})

class WizardRuns:
    def __init__(self, root, input_root, output_root, native, lifecycle, legacy_busy, selection_parser, variants):
        self.root,self.input_root,self.output_root=map(Path,(root,input_root,output_root))
        self.native,self.lifecycle,self.legacy_busy=native,lifecycle,legacy_busy
        self.selection_parser,self.variants=selection_parser,variants
        self.tasks={}
        self.runs={}
        self.image_source_resolver=None

    def path(self, ident):
        if not isinstance(ident,str) or not re.fullmatch("[0-9a-f]{32}",ident):
            raise ValueError("Unknown wizard run.")
        return self.root/(ident+".json")

    def save(self, run):
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.path(run["id"])
        temporary=path.with_suffix(".tmp")
        temporary.write_text(json.dumps(run,ensure_ascii=False,indent=2),encoding="utf-8")
        temporary.replace(path)

    def get(self, ident):
        if ident in self.runs:return self.runs[ident]
        try:run=json.loads(self.path(ident).read_text(encoding="utf-8"))
        except FileNotFoundError:raise ValueError("This wizard run could not be found.") from None
        self.runs[ident]=run
        if run.get("status")=="running":
            # A browser refresh keeps the task; a server restart needs explicit
            # recovery. A still-queued prompt is adopted, never submitted twice.
            pending=run.get("pending")
            if pending and (pending["prompt_id"] in self.native.active_ids() or self.native.history(pending["prompt_id"])):
                self.tasks[ident]=asyncio.create_task(self.recover(run))
            else:
                run.update(status="interrupted",error="Comfy restarted. Retry the stage; completed files are retained.")
                self.save(run)
        return run

    def selection(self, value):
        chosen=self.selection_parser(json.dumps(value),{k:set(v[1]) for k,v in self.variants.items() if k!="quad_detail"})
        return {"schema":"mumblebox.export-selection/1","variants":{k:{"formats":list(v)} for k,v in chosen.variants.items()}}

    def validate(self, data):
        if not isinstance(data,dict) or not isinstance(data.get("name",""),str):
            raise ValueError("Enter an asset name.")
        name=data.get("name","").strip()
        if not name or len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError("Enter an asset name of 1-100 characters.")
        refs=copy.deepcopy(data.get("references",[]))
        category=data.get("category","characters")
        turnaround_model=data.get("turnaround_model","qwen21")
        method=data.get('method','turnaround')
        if method not in ('turnaround','single-image'):raise ValueError('Choose an available mesh method.')
        single=method=='single-image'
        if single:
            from ..single_image.definition import validate_references
            validate_references(refs)
        bound=bind_references(category,refs,turnaround_model)
        for item in refs:
            path=owned_path(self.input_root,self.input_root/item["filename"])
            if not path.is_file():raise ValueError("An uploaded reference is missing. Upload it again.")
            if path.stat().st_size>20*1024**2:raise ValueError("Use references smaller than 20 MB each.")
            from PIL import Image
            with Image.open(path) as image:
                if image.width*image.height>40_000_000:raise ValueError("Use a reference smaller than 40 megapixels.")
                image.verify()
            item["sha256"]=digest(path)
        if re.search(r"[<>:\"/\\|?*]",name) or name.split(".")[0].upper() in {"CON","PRN","AUX","NUL",*("COM"+str(i) for i in range(1,10)),*("LPT"+str(i) for i in range(1,10))}:
            raise ValueError("Use an asset name without path separators or reserved Windows names.")
        profile=data.get("profile","default")
        overrides=copy.deepcopy(data.get("overrides",{}))
        settings_resolver=resolve_settings
        if single:
            from ..single_image.definition import resolve_settings as settings_resolver
            bound={'prompt':'','recipe':'official-single-image','guidance':'One original reference; three-quarter view recommended.'}
        return dict(method=method,name=name,slug=re.sub("[^a-zA-Z0-9_-]+","-",name).strip("-")[:60] or "asset",
                    category=category,references=refs,profile=profile,overrides=overrides,
                    settings=settings_resolver(profile,overrides),
                    selection=self.selection(data.get("selection",DEFAULT_SELECTION)),
                    reference_prompt=bound["prompt"],turnaround_model=turnaround_model,
                    turnaround_recipe=bound["recipe"],turnaround_guidance=bound["guidance"],
                    image_creation=self.image_source_resolver(data.get('image_creation'),refs) if self.image_source_resolver else None)

    def create(self, data):
        run={**self.validate(data),"id":uuid.uuid4().hex,"created":time.time(),"status":"idle",
             "stage":"","stages":{},"checkpoints":{},"previews":{},"outputs":{},"events":[],
             "version":VERSION,"error":"","cancel":False}
        self.runs[run["id"]]=run
        self.save(run)
        return self.public(run)

    def update(self, ident, data):
        run=self.get(ident)
        if ident in self.tasks:raise ValueError("Wait for this stage or cancel it before changing its inputs.")
        revised=self.validate(data)
        if revised.get("method")!=run.get("method","turnaround"):raise ValueError("Start a new asset to change its workflow method.")
        if ident in self.tasks:raise ValueError("This stage started while the inputs were being checked. Wait or cancel before changing them.")
        run.update(revised)
        # Invalidate the current view of stale descendants, never their files.
        keys={"turnaround":["sheet","front","left","back","right"],"geometry":["decoded"],
              "refinement":["refined","clean"],"texture":["texture"],"balanced":["balanced"],
              "compact":["compact"],"quads":["quads","quad_manifest"],"print":["print"],"package":[]}
        if run.get("method")=="single-image":keys["geometry"].append("front")
        for stage,receipt in list(run["stages"].items()):
            if stage=="package" or receipt["fingerprint"]!=self.fingerprint(run,stage):
                for key in keys[stage]:
                    run["checkpoints"].pop(key,None);run["previews"].pop(key,None)
                run["stages"].pop(stage,None)
        run.pop("package",None)
        self.save(run)
        return self.public(run)

    def public(self, run):
        # No model state, credentials or unbounded history crosses this boundary.
        fields=("id","name","category","references","profile","overrides","settings","selection","status",
                "stage","error","previews","package","cleanup","version","pending","events","reference_prompt","measurements","geometry_audit","dependency",
                "method","quad_report","turnaround_model","turnaround_recipe","turnaround_guidance","operation","request_id","image_creation")
        result=copy.deepcopy({k:run[k] for k in fields if k in run})
        if run.get("checkpoints",{}).get("print") and not run.get("package",{}).get("grounded_previews",{}).get("print"):
            path=Path(run["checkpoints"]["print"])
            relative=path.relative_to(self.output_root)
            result.setdefault("previews",{})["print"]=view_url({"filename":path.name,"subfolder":relative.parent.as_posix(),"type":"output"})
        result["completed"]=list(run["stages"])
        result["active"]=run["id"] in self.tasks
        result["progress"]=progress_snapshot(run)
        if run.get("dependency"):
            from .readiness import download_progress
            result["dependency"]={**run["dependency"],**download_progress(run["id"])}
        result["outputs"]=copy.deepcopy(run.get("outputs",{}))
        if run.get("method")!="single-image" and run.get("references") and run.get("settings"):
            result["turnaround"]=model_spec(run.get("turnaround_model","qwen21"))
        if "geometry_audit" not in result:
            saved=run.get("outputs",{}).get("2015",{}).get("text",[])
            if saved:
                try:result["geometry_audit"]=json.loads(saved[0])
                except (TypeError,ValueError):pass
        return result

    def fingerprint(self, run, stage):
        if run.get('method')=='single-image':
            from ..single_image.policy import fingerprint
            return fingerprint(run,stage,self.input_root)
        settings={k:run["settings"][k] for k in STAGE_KEYS[stage]}
        if stage=="turnaround":
            # Detect a file replaced outside the wizard as well as changed notes/order.
            refs=[{**r,"sha256":digest(owned_path(self.input_root,self.input_root/r["filename"]))} for r in run["references"]]
            inputs=[run["category"],refs]
            # Keep the original Qwen character cache identity. Changed recipes
            # bind the exact model and prompt so a different model cannot reuse it.
            model_id=run.get("turnaround_model","qwen21")
            if model_id!="qwen21" or run["category"]!="characters":
                bound=bind_references(run["category"],run["references"],model_id)
                inputs += [model_id,bound["recipe"],bound["prompt"]]
        elif stage=="package":
            inputs=[run["selection"],run.get("metadata")]
        else:
            inputs=[self.fingerprint(run,s) for s in DEPENDENCIES[stage]]
        return signature([VERSION,stage,settings,inputs])

    def fresh(self, run, stage):
        old=run["stages"].get(stage)
        return bool(old and old["fingerprint"]==self.fingerprint(run,stage) and
                    all(Path(p).is_file() and digest(p)==sha for p,sha in old["files"].items()))

    def start(self, ident, operation, client_id, request_id=None):
        run=self.get(ident)
        if operation not in ("turnaround","mesh","finish","rocket"):raise ValueError("Choose a wizard stage.")
        if request_id is not None:
            if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",request_id):
                raise ValueError("Invalid start request identifier.")
            if request_id==run.get("request_id"):
                if operation!=run.get("operation"):raise ValueError("This request identifier belongs to a different operation.")
                return self.public(run)
        if self.tasks or self.native.active_ids() or self.legacy_busy():
            raise ValueError("Another Comfy or Foundry job is active. Wait for it to finish.")
        if run.get("method")!="single-image" and operation in ("mesh","finish") and not self.fresh(run,"turnaround"):
            raise ValueError("Generate and review the current four views first.")
        if operation=="finish" and not self.fresh(run,"refinement"):
            raise ValueError("Generate the refined mesh with the current settings first.")
        if run.get('method')=='single-image' and operation=='turnaround':raise ValueError('Single Image does not use turnaround generation.')
        run.update(status="running",stage="preparing",error="",cancel=False,operation=operation,client_id=client_id,request_id=request_id)
        self.save(run)
        self.tasks[ident]=asyncio.create_task(self.execute(run,operation))
        return self.public(run)

    def cancel(self, ident):
        run=self.get(ident)
        run["cancel"]=True
        if run.get("pending"):self.native.cancel(run["pending"]["prompt_id"])
        if run.get("dependency"):
            from .readiness import cancel_download
            cancel_download(ident)
        self.save(run)
        return self.public(run)

    def require_not_cancelled(self, run):
        if run.get("cancel"):raise asyncio.CancelledError()

    def event(self, run, text):
        run["events"]=(run["events"]+[{"time":time.time(),"text":text}])[-40:]
        self.save(run)

    async def recover(self, run):
        try:
            await self.accept_pending(run)
            run.update(status="interrupted",error="The interrupted stage was recovered. Continue to finish the remaining stages.")
        except Exception as error:run.update(status="failed",error=str(error))
        finally:
            run.pop("pending",None)
            self.tasks.pop(run["id"],None)
            self.save(run)

    async def execute(self, run, operation):
        try:
            await self.prepare_dependencies(run, operation)
            # stage() reuses validated checkpoints, so Rocket can enter from any page.
            # The backend owns continuation; it never depends on a browser staying open.
            if run.get("method")!="single-image" and operation in ("turnaround","rocket"):
                await self.stage(run,"turnaround")
            if operation in ("mesh","rocket"):
                await self.stage(run,"geometry")
                await self.stage(run,"refinement")
            if operation in ("finish","rocket"):
                selected=run["selection"]["variants"]
                if any(k!="print" for k in selected):
                    await self.stage(run,"texture")
                for variant,stage in (("game_balanced","balanced"),("game_compact","compact"),
                                       ("quad_light","quads"),("print","print")):
                    if variant in selected:await self.stage(run,stage)
                run["metadata"]=await asyncio.to_thread(self.metadata,run)
                await self.stage(run,"package",reuse=False)
                # Publication precedes indexing and cleanup. No durable output is scratch.
                from ...receipts import sync
                if hasattr(self,"library"):await asyncio.to_thread(sync,self.library)
            run.update(status="cleaning",error="")
        except asyncio.CancelledError:
            run.update(status="cancelled",error="Generation cancelled. Completed stages and saved files are retained.")
        except InterruptedError as error:
            run.update(status="cancelled" if run.get("cancel") else "failed",error=str(error))
        except Exception as error:
            run.update(status="failed",error=str(error))
        finally:
            run.pop("pending",None)
            run.pop("dependency",None)
            try:
                if not self.native.active_ids():
                    run["cleanup"]=await self.lifecycle().release("Foundry "+operation+" complete")
            except Exception as error:
                run["cleanup"]={"status":"failed","error":str(error)}
            if run["status"]=="cleaning":run["status"]="complete"
            self.tasks.pop(run["id"],None)
            self.save(run)

    async def prepare_dependencies(self, run, operation):
        from .readiness import ensure, required_stages
        self.require_not_cancelled(run)
        run["stage"] = "preparing"
        self.event(run, "Preparing models for the remaining selected workflow before generation.")
        loop = asyncio.get_running_loop()
        def progress(value):
            loop.call_soon_threadsafe(lambda: run.update(dependency=value))
        if run.get('method')=='single-image':
            from ..single_image.definition import required_stages
        for stage in required_stages(operation, run["selection"]):
            if await asyncio.to_thread(self.fresh, run, "geometry" if stage=="single_geometry" else stage):
                continue
            self.require_not_cancelled(run)
            await asyncio.to_thread(ensure, stage, self.root, lambda: run.get("cancel", False),
                                    run["id"], progress, run.get("turnaround_model", "qwen21"),run.get("settings",{}).get("geometry_model","pixal3d"))
        run.pop("dependency", None)
        self.require_not_cancelled(run)

    async def stage(self, run, stage, reuse=True):
        self.require_not_cancelled(run)
        if reuse and await asyncio.to_thread(self.fresh,run,stage):
            self.event(run,"Reused saved "+stage+" stage.")
            return
        run["stage"]=stage
        self.event(run,"Starting "+stage+".")
        await self.lifecycle().barrier()
        await self.lifecycle().release("before Foundry "+stage)
        self.require_not_cancelled(run)
        from .readiness import ensure
        loop=asyncio.get_running_loop()
        def progress(value):
            run["dependency"]=value
        run["dependency"]={"phase":"checking required models"}
        await asyncio.to_thread(ensure,"single_geometry" if stage=="geometry" and run.get("method")=="single-image" else stage,self.root,lambda:run.get("cancel",False),run["id"],
                                lambda value:loop.call_soon_threadsafe(progress,value),run.get("turnaround_model","qwen21"),run.get("settings",{}).get("geometry_model","pixal3d"))
        run.pop("dependency",None)
        self.require_not_cancelled(run)
        graph=compile_stage(stage,run)
        ident=str(uuid.uuid4())
        pending={"stage":stage,"prompt_id":ident,"fingerprint":self.fingerprint(run,stage),
                 "nodes":list(graph),"started":time.time()}
        # Write before submission so a browser/server interruption is recoverable.
        run["pending"]=pending
        self.save(run)
        await self.native.submit(graph,ident,run.get("client_id",""))
        await self.accept_pending(run)
        self.require_not_cancelled(run)

    def file_entry(self, entry):
        if entry.get("type")!="output":raise ValueError("A durable output was expected.")
        path=owned_path(self.output_root,self.output_root/entry.get("subfolder","")/entry["filename"])
        if not path.is_file():raise ValueError("A completed stage output is missing.")
        return path

    async def accept_pending(self, run):
        pending=run["pending"]
        history=await self.native.wait(pending["prompt_id"],7200,lambda:run.get("cancel",False))
        self.require_not_cancelled(run)
        status=history.get("status",{})
        if status.get("status_str")!="success":
            errors=[str(m[1].get("exception_message","")) for m in status.get("messages",[]) if m[0]=="execution_error"]
            raise ValueError("Comfy could not finish "+pending["stage"]+": "+("; ".join(errors) or status.get("status_str","interrupted")))
        outputs=history.get("outputs",{})
        if run.get('method')=='single-image':
            outputs={str(int(k)-500000):v for k,v in outputs.items()}
        stage=pending["stage"]
        # Keep an immutable production record independently of the editable draft.
        record=self.root/run["id"]/"stages"/(pending["prompt_id"]+".json")
        record.parent.mkdir(parents=True,exist_ok=True)
        evidence={"stage":stage,"prompt_id":pending["prompt_id"],"fingerprint":pending["fingerprint"],
                  "settings":run.get("settings",{}),"references":run.get("references",[]),
                  "reference_prompt":run.get("reference_prompt"),"submitted_prompt":history.get("prompt"),
                  "turnaround_model":run.get("turnaround_model","qwen21"),"turnaround_recipe":run.get("turnaround_recipe"),
                  "outputs":outputs,"completed":time.time()}
        record.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
        paths=[]
        def saved(node,key,kind="3d"):
            entry=output_entry(outputs,node,kind)
            path=self.file_entry(entry)
            run["checkpoints"][key]=str(path) if kind=="3d" else (Path(entry.get("subfolder",""))/entry["filename"]).as_posix()+" [output]"
            run["previews"][key]=view_url(entry)
            paths.append(path)
        if stage=="turnaround":
            saved("412","sheet","images")
            for node,view in (("340","front"),("344","left"),("343","back"),("346","right")):
                saved(node,view,"images")
            from PIL import Image
            for path in paths[1:]:
                with Image.open(path).convert("RGB") as image:
                    if image.getbbox() is None:raise ValueError("A turnaround crop is empty. Regenerate or revise the reference.")
        elif stage=="geometry":
            saved("382","decoded")
            if run.get('method')=='single-image':saved('340','front','images')
        elif stage=="refinement":
            saved("2005","refined")
            saved("2017","clean")
            if outputs.get("2015",{}).get("text"):
                run["geometry_audit"]=json.loads(outputs["2015"]["text"][0])
        elif stage=="texture":saved("2024","texture")
        elif stage=="balanced":saved("2034","balanced")
        elif stage=="compact":saved("2044","compact")
        elif stage=="print":
            report=json.loads(outputs["2050"]["text"][0])
            path=owned_path(self.output_root,report["output"])
            run["checkpoints"]["print"]=str(path)
            run["print_report"]=report
            paths.append(path)
        elif stage=="quads":
            report=json.loads(outputs["3001"]["text"][0])
            run["quad_report"]=report
            manifest=owned_path(self.output_root,Path(report["export_dir"])/"manifest.json")
            run["checkpoints"]["quad_manifest"]=str(manifest)
            paths.append(manifest)
            entry={"filename":"runtime.glb","subfolder":manifest.parent.relative_to(self.output_root).as_posix(),"type":"output"}
            run["previews"]["quads"]=view_url(entry)
        elif stage=="package":
            report=json.loads(outputs["3010"]["text"][1])
            path=owned_path(self.output_root,report["archive_path"])
            for key,filename in report.get('grounded_previews',{}).items():
                artifact=owned_path(self.output_root,filename);relative=artifact.relative_to(self.output_root)
                run['previews'][key]=view_url({'filename':artifact.name,'subfolder':relative.parent.as_posix(),'type':'output'})
            run["package"]={**report,"download":"/mumblebox-foundry/v1/wizard/runs/"+run["id"]+"/package"}
            paths.append(path)
            import zipfile
            with zipfile.ZipFile(path) as archive:
                manifest=json.loads(archive.read("Metadata/manifest.json"))
            run["measurements"]={v["id"]:{"measurements":v["measurements"],"validations":v["validations"],"directory":v["directory"]} for v in manifest["variants"]}
        run["outputs"].update(outputs)
        run["stages"][stage]={"fingerprint":pending["fingerprint"],"files":{str(p):digest(p) for p in paths},
                              "prompt_id":pending["prompt_id"],"nodes":pending["nodes"],"record":str(record),"seconds":time.time()-pending["started"]}
        run.pop("pending",None)
        self.event(run,"Completed "+stage+"; saved output verified.")

    def metadata(self, run):
        if run.get('method')=='single-image':
            from ..single_image.policy import metadata
            return metadata(run)
        spec=model_spec(run.get("turnaround_model","qwen21"))
        resources=spec["resources"]+["pixal3d","trellis2","hi3d","pymeshlab","dinov3","birefnet","pixelartistry"]
        receipts=[]
        keys={"detailed":"texture","game_balanced":"balanced","game_compact":"compact","print":"print"}
        for variant in run["selection"]["variants"]:
            if variant=="quad_light":
                path=Path(run["checkpoints"]["quad_manifest"]).parent/"editable-quads.blend"
            else:path=Path(run["checkpoints"][keys[variant]])
            used=resources+([] if variant=="print" else ["trellis_wrapper"])
            if variant=="print" and run.get("print_report",{}).get("contact_repair"):used+=["meshlib"]
            if variant=="quad_light":used+=["quadriflow"]
            receipts.append({"variant_id":variant,"sha256":digest(path),"resources":used,
                "validation":[{"name":"Current wizard production","status":"matched",
                 "note":"File hash bound to run "+run["id"]+"; completed stage requests and inputs retained."}]})
        lineage={"run_id":run["id"],"workflow_version":VERSION,"category":run["category"],
                 "profile":run["profile"],"settings":run["settings"],"overrides":run["overrides"],
                 "reference_prompt":run["reference_prompt"],"references":run["references"],
                 "selection":run["selection"],"stages":{k:{x:v[x] for x in ("fingerprint","prompt_id","seconds") if x in v} for k,v in run["stages"].items() if k!="package"}}
        bound=bind_references(run["category"],run["references"],spec["id"])
        lineage["turnaround"]={k:spec[k] for k in ("id","name","steps","cfg","width","height","sampler","scheduler","source","license","license_url")}
        lineage["turnaround"].update(recipe=bound["recipe"],guidance=bound["guidance"],prompt_source=bound["source"],seed=run["settings"]["turnaround_seed"])
        model_lock=json.loads(Path(__file__).resolve().parents[3].joinpath("models.lock.json").read_text(encoding="utf-8"))
        lock=model_lock["models"]
        lineage["models"]={key:{field:lock[key][field] for field in ("repo","file","revision","sha256")}
                           for key in (*spec["keys"],"birefnet","pixal_multiview","shape_vae","dino")}
        if any(variant != "print" for variant in run["selection"]["variants"]):
            lineage["texture_models"] = [{field:item[field] for field in ("name","repo","file","revision","sha256")}
                                        for item in model_lock["worker_models"]["trellis_texture"]]
        if run.get('image_creation'):lineage['image_creation']=run['image_creation']
        return {"workflow_version":VERSION,"receipts":receipts,"production":lineage,"warnings":run.get("quad_report",{}).get("warnings",[])}
