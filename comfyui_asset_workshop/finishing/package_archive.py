"""Publication of catalog-driven asset packages; never mutates source assets."""
import json,hashlib,zipfile,re,shutil,uuid,copy
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import unquote,urlsplit
from dataclasses import dataclass,asdict
from .package_catalog import *
from .package_readme import render_readme
HERE=Path(__file__).parent
MANIFEST="Metadata/manifest.json"
def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def resolved_member(root,relative):
    safe_relative(relative);p=root/relative
    if not p.resolve().is_relative_to(root.resolve()):raise ValueError("Package dependency escapes staging")
    return p
def validate_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();validate_paths(names)
        if z.testzip():raise ValueError("Archive CRC failed")
        m=json.loads(z.read(MANIFEST));files=m["files"]
        expected={f["path"] for f in files}
        if set(names)!=expected:raise ValueError("Archive members differ from catalog")
        for f in files:
            if f["path"]==MANIFEST:
                if f["bytes"]!=len(z.read(MANIFEST)):raise ValueError("Manifest byte size differs")
                continue
            raw=z.read(f["path"])
            if len(raw)!=f["bytes"] or hashlib.sha256(raw).hexdigest()!=f["sha256"]:raise ValueError("Package checksum failed: "+f["path"])
        doc=z.read("README.md").decode("utf-8")
        links=re.findall(r"\]\(([^)]+)\)",doc)
        local=[unquote(x) for x in links if not x.startswith("#") and not urlsplit(x).scheme]
        if set(local)!=expected-{"README.md"}:raise ValueError("README file inventory differs from archive")
        if len(local)!=len(set(local)):raise ValueError("README lists a file more than once")
        by={f["path"]:f for f in files}
        for f in files:
            for dep in f["depends_on"]:
                if dep not in by:raise ValueError("Required package dependency missing: "+dep)
        return {"file_count":len(names),"schema":m["schema"],"variants":[v["id"] for v in m["variants"]]}
def publish_archive(catalog,root,archive,check_interrupt):
    root=Path(root);archive=Path(archive);partial=archive.with_suffix(".zip.partial")
    if archive.exists() or partial.exists():raise FileExistsError("Package destination already exists")
    check_interrupt()
    validate_paths([f.path for f in catalog.files])
    for f in catalog.files:
        if f.path==MANIFEST:continue
        p=resolved_member(root,f.path)
        if not p.is_file():raise FileNotFoundError("Required file missing: "+f.path)
        f.bytes=p.stat().st_size;f.sha256=digest(p)
    # The renderer sees the manifest record but not its own README record.
    (root/"README.md").write_text(render_readme(catalog),encoding="utf-8",newline="\n")
    catalog.files.append(FileRecord("README.md","documentation",None,"Directory inventory and recorded asset specifications.","md","catalog",bytes=(root/"README.md").stat().st_size,sha256=digest(root/"README.md")))
    mp=root/MANIFEST;mp.parent.mkdir(parents=True,exist_ok=True)
    own=next(f for f in catalog.files if f.path==MANIFEST)
    for _ in range(8):
        payload=json.dumps(catalog.to_dict(),indent=2,ensure_ascii=False).encode("utf-8")
        if own.bytes==len(payload):break
        own.bytes=len(payload)
    else:raise RuntimeError("Manifest size did not converge")
    mp.write_bytes(payload)
    try:
        with zipfile.ZipFile(partial,"x",zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            for f in sorted(catalog.files,key=lambda f:f.path):
                check_interrupt();z.write(resolved_member(root,f.path),f.path)
        validate_archive(partial);check_interrupt();partial.replace(archive)
    finally:
        if partial.exists():partial.unlink()
    return archive

@dataclass
class BuildResult:
    archive_path:str
    export_id:str
    selected_variants:list
    file_count:int
    bytes:int
    sha256:str
    warnings:list

def build_archive(sources,selection,identity,metadata,output_root,worker,check_interrupt):
    ident=uuid.uuid4().hex
    asset=metadata.get("asset_name") or "Asset"
    slug=re.sub("[^A-Za-z0-9_.-]+","-",metadata.get("run_name") or asset).strip("-.")[:80] or "asset"
    root=Path(output_root)/(slug+"-"+ident[:8]);root.mkdir(parents=True,exist_ok=False)
    job=Path(metadata["_job_root"])/ident;job.mkdir(parents=True,exist_ok=False)
    from .owned_scratch import register
    register(job,["relocated"],"Relocated import verification copy; published files are retained")
    selected=dependency_closure(selection,sources)
    original_hashes={str(Path(p).resolve()):digest(p) for s in selected.values() for p in s.files.values() if Path(p).is_file()}
    req={"job":str(job),"export_dir":str(root),"grounding":metadata.get("grounding"),"variants":{k:{"directory":VARIANTS[k][0],"formats":list(selection.variants[k]),"sources":{role:str(Path(p).resolve()) for role,p in s.files.items()}} for k,s in selected.items()}}
    (job/"request.json").write_text(json.dumps(req,indent=2),encoding="utf-8")
    check_interrupt();worker(req,"package",check_interrupt)
    report=json.loads((job/"package-report.json").read_text(encoding="utf-8"))
    files=[FileRecord(**f) for f in report["files"]]
    if metadata.get("production"):
        production=root/"Metadata"/"production.json"
        production.parent.mkdir(parents=True,exist_ok=True)
        production.write_text(json.dumps(metadata["production"],indent=2,ensure_ascii=False),encoding="utf-8")
        files.append(FileRecord("Metadata/production.json","metadata",None,
            "Actual run settings, ordered reference hashes, selected outputs and completed stage identities.","json","production"))
        if metadata['production'].get('method')=='3d-guided/v1':
            cameras=root/'Metadata/cameras.json'
            cameras.write_text(json.dumps(metadata['production']['camera_manifest'],indent=2),encoding='utf-8')
            files.append(FileRecord('Metadata/cameras.json','metadata',None,
                'Measured Blender cameras and inherited enhanced-view calibration. Enhancement camera adherence requires visual review.',
                'json','cameras'))
    variants=[VariantRecord(**v) for v in report["variants"]]
    # Accept existing final-stage receipts only when their input file digest matches.
    metadata=copy.deepcopy(metadata)
    supplied_warnings=metadata.get("warnings",[])
    warnings=[str(item)[:2000] for item in supplied_warnings[:100]] if isinstance(supplied_warnings,list) else []
    resource_ids={"blender","comfyui"}
    for v in variants:
        src=selected[v.id]
        hashes={digest(p) for p in src.files.values() if Path(p).is_file()}
        receipts=list(src.receipts)+metadata.get("receipts",[])
        for receipt in receipts:
            if receipt.get("variant_id")!=v.id or receipt.get("sha256") not in hashes:continue
            for group in ("topology","coordinates"):
                if isinstance(receipt.get(group),dict):v.measurements[group]=receipt[group]
            for item in receipt.get("validation",[]):
                v.validations.append({"name":item["name"],"status":item["status"],"note":item.get("note","")})
            v.limitations.extend(str(x) for x in receipt.get("limitations",[]))
            resource_ids.update(receipt.get("resources",[]))
        if not any(r.get("variant_id")==v.id and r.get("sha256") in hashes and r.get("resources") and r.get("provenance_scope")!="finishing_only" for r in receipts):
            warnings.append(v.directory+" upstream production provenance was not supplied or did not match the input file.")
    registry=json.loads((HERE/"package_resources.json").read_text(encoding="utf-8"))
    resources=[]
    notice_root=HERE.parent/"licenses/pipeline"
    for rid in sorted(resource_ids):
        if rid not in registry:raise ValueError("Unregistered production resource: "+rid)
        r=registry[rid]
        if r.get("note"):warnings.append(r["note"])
        resources.append({k:r.get(k) for k in ("id","stage","name","version","source","license","license_url","license_summary")})
        if rid=="blender":resources[-1]["version"]=report["blender"]
        safe_url(r.get("source"))
        safe_url(r.get("license_url"))
        for filename in r.get("notices",[]):
            p=notice_root/safe_relative(filename)
            if not p.is_file():raise FileNotFoundError("Resource notice missing: "+filename)
            rel="Licenses/"+filename
            if any(f.path==rel for f in files):continue
            target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            files.append(FileRecord(rel,"license",None,r["name"]+" retained license or notice.",p.suffix.lstrip("."),"notice"))
        if not r.get("notices"):
            warnings.append(r["name"]+": retained notice text is not configured; the source link identifies the resource.")
    identity=copy.deepcopy(identity)
    if identity.get("terms"):
        term=identity["terms"];p=(HERE/safe_relative(term["source"])).resolve()
        if not p.is_relative_to(HERE.resolve()) or not p.is_file():raise ValueError("Configured Mumblebox terms file is missing or outside the package configuration")
        rel="Licenses/Mumblebox/TERMS.md";target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        files.append(FileRecord(rel,"license",None,"Approved Mumblebox terms.","md","terms"))
        identity["terms"]={"path":rel,"version":term.get("version"),"sha256":digest(p)}
    else:warnings.append("Mumblebox terms have not been supplied.")
    files.append(FileRecord(MANIFEST,"metadata",None,"Structured inventory, relationships, measured specifications, production resources and file checksums.","json","manifest"))
    meta={"asset_name":asset,"export_id":ident,"created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"workflow_version":metadata.get("workflow_version"),"warnings":warnings,
          "production":{key:metadata["production"][key] for key in ("category","turnaround","method","selected_view_ids","reference_view_id","camera_manifest","source_download") if key in metadata.get("production",{})}}
    catalog=build_catalog(files,variants,resources,identity,meta)
    # Native verification is run against a relocated copy before the final ZIP is published.
    relocated=job/"relocated";shutil.copytree(root,relocated)
    req["verify_root"]=str(relocated);req["expected_report"]=report
    (job/"request.json").write_text(json.dumps(req,indent=2),encoding="utf-8")
    worker(req,"package_verify",check_interrupt)
    verified=json.loads((job/"package-verification.json").read_text(encoding="utf-8"))
    for v in catalog.variants:
        v.validations.append({"name":"Relocated file import and texture references","status":"pass","note":verified["variants"][v.id]["note"]})
    for path,h in original_hashes.items():
        if digest(path)!=h:raise RuntimeError("Source changed during packaging")
    archive=root.with_suffix(".zip");publish_archive(catalog,root,archive,check_interrupt)
    result=BuildResult(str(archive),ident,list(selection.variants),len(catalog.files),archive.stat().st_size,digest(archive),warnings)
    (job/"result.json").write_text(json.dumps(asdict(result),indent=2),encoding="utf-8")
    return result
