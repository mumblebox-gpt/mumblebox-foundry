"""One factual root document rendered exclusively from the package catalog."""
import html,re
from urllib.parse import quote
def text(value):
    return html.escape(str(value),quote=False).replace("|",r"\|").replace("\r"," ").replace("\n"," ").replace(chr(96),"\\"+chr(96)).replace("[",r"\[").replace("]",r"\]")
def fmt(v):
    if v is None:return "Not recorded"
    if isinstance(v,bool):return "Yes" if v else "No"
    if isinstance(v,int):return f"{v:,}"
    if isinstance(v,float):return f"{v:.6g}"
    if isinstance(v,(list,tuple)):return " × ".join(fmt(x) for x in v)
    return text(v)
def anchor(path):return "dir-"+re.sub(r"[^a-z0-9]+","-",path.lower()).strip("-")
def link(path,label=None):return "["+text(label or path)+"]("+quote(path,safe="/._-")+")"
def file_table(files,prefix=""):
    out=["| Filename | Contents |","|---|---|"]
    for f in sorted(files,key=lambda f:(f.kind=="texture",f.path.casefold())):out.append("| "+link(f.path,f.path.removeprefix(prefix))+" | "+text(f.description)+" |")
    return out
LABELS={"vertices":"Vertices","triangles":"Triangles","quads":"Quads","ngons":"N-gons","polygons":"Total polygons","uv_layers":"UV layers","objects":"Mesh objects","dimensions":"Dimensions (X × Y × Z)","units":"Units","up_axis":"Up axis","boundary_edges":"Boundary edges","nonmanifold_edges":"Non-manifold edges","degenerate_triangles":"Degenerate triangles","components":"Connected components","watertight":"Closed geometry","winding_consistent":"Consistent winding"}
def measurement_lines(m):
    out=[]
    groups=[("Geometry",m.get("geometry") or {k:v for k,v in m.items() if k in LABELS})]
    groups += [(title,m.get(key,{})) for title,key in (("Authoring geometry","authoring"),("Runtime geometry","runtime"),("Dimensions and coordinates","coordinates"),("Recorded topology","topology"),("Grounding","grounding"))]
    for title,data in groups:
        if data:
            out+=["**"+title+"**","","| Measurement | Value |","|---|---:|"]
            out+=["| "+LABELS.get(k,text(k.replace("_"," ").title()))+" | "+fmt(v)+" |" for k,v in data.items() if not isinstance(v,dict)]+[""]
    maps=m.get("textures",[])
    if maps:
        out+=["**Texture specifications**","","| File | Dimensions | Interpretation |","|---|---:|---|"]
        for item in maps:out+=["| "+text(item["path"])+" | "+fmt(item.get("dimensions"))+" | "+text(item.get("interpretation","Not recorded"))+" |"]
        out+=[""]
    return out
def render_readme(catalog):
    c=catalog;lines=["# "+text(c.asset_name)+" — "+text(c.project_identity.get("name") or "Mumblebox")+" Asset Package","",
      "This package contains the exported assets and associated files listed below. Each directory entry describes its contents, intended use, filenames and recorded specifications.","",
      "| Package information | Value |","|---|---|","| Asset | "+text(c.asset_name)+" |","| Export date (UTC) | "+text(c.created_utc)+" |","| Export identifier | "+text(c.export_id)+" |","| Workflow version | "+fmt(c.workflow_version)+" |","| Package schema | "+text(c.schema)+" |","","All file paths are relative to the package root.","","## Directory index",""]
    dirs=[v.directory for v in c.variants]
    for d in ("Metadata/","Licenses/"):
        if any(f.path.startswith(d) for f in c.files):dirs.append(d)
    lines+=["- ["+text(d)+"](#"+anchor(d)+")" for d in dirs]+["","## Directory contents",""]
    for v in c.variants:
        lines+=['<a id="'+anchor(v.directory)+'"></a>',"### "+text(v.directory),"",text(v.description)+(("\n\n"+text(v.intended_use)) if v.intended_use else ""),"","**Files**",""]
        lines+=file_table([f for f in c.files if f.variant_id==v.id],v.directory)+[""]+measurement_lines(v.measurements)
        lines+=["**Recorded validation**",""]
        if v.validations:
            for val in v.validations:
                r=val if isinstance(val,dict) else vars(val)
                lines+=["- "+text(r["name"])+": "+text(r["status"].replace("_"," "))+(". "+text(r["note"]).rstrip(".") if r.get("note") else "")+"."]
        else:lines+=["- Additional validation: Not recorded."]
        if v.limitations:lines+=["","**Recorded limitations**",""]+["- "+text(x) for x in v.limitations]
        lines+=[""]
    for directory,desc in (("Metadata/","Contains the structured inventory of the included files, their relationships, measurements, production resources and integrity records."),("Licenses/","Contains retained license and notice documents associated with the resources recorded in this export. They are separate from Mumblebox terms and any explicitly supplied finished-asset license.")):
        fs=[f for f in c.files if f.path.startswith(directory)]
        if not fs:continue
        lines+=['<a id="'+anchor(directory)+'"></a>',"### "+directory,"",desc,"","**Files**",""]+file_table(fs,directory)+["","**Specifications**",""]
        if directory=="Metadata/":lines+=["- Format: JSON, UTF-8.","- File paths: relative to package root.","- Integrity algorithm: SHA-256.","- The manifest records all other archive members, including README.md. It excludes its own checksum."]
        else:lines+=["- Included documents: "+str(len(fs))+".","- Retained source texts are not rewritten by the catalog."]
        lines+=[""]
    lines+=["## Production record",""]
    if c.production.get('method')=='3d-guided/v1':
        lines+=['### 3D-Guided method','',
            'A single-image rough mesh supplied measured Blender views and depth guides. Enhanced views were selected for reconstruction, followed by refinement, cleanup and final texturing.','',
            '- Selected views: '+text(', '.join(c.production.get('selected_view_ids',[])))+'.',
            '- Finishing reference: '+text(c.production.get('reference_view_id','Not recorded'))+'.',
            '- Numerical camera records are listed in the Metadata directory. These describe the renderer targets; camera adherence after enhancement requires visual review.',
            '- Original references, concept edits, prompts and intermediate meshes are retained locally. The separate private production download includes those files.','']
    creation=c.production.get('image_creation')
    if creation:
        lines += ['### Originating reference images','','Accepted images created in Foundry and used as references for this asset.','',
                  '| View | Image model | Seed | Recorded license |','|---|---|---|---|']
        for image in creation.get('images',[]):
            p=image['provenance'];terms=p.get('model_license',{})
            lines += ['| '+text(image['side'])+' | '+text(p.get('profile','Not recorded'))+' | '+fmt(p.get('seed'))+' | '+text(terms.get('label','Not recorded'))+' |']
        lines += ['']
        for image in creation.get('images',[]):
            p=image['provenance'];terms=p.get('model_license',{})
            if terms.get('url'):lines += ['',text(image['side'].title())+' model source and terms: '+text(terms['url']),'']
            checkpoint=p.get('checkpoint',{})
            if checkpoint:lines += ['- Image checkpoint: '+text(checkpoint.get('model_name','External checkpoint'))+'. Source: '+text(checkpoint.get('source_url','Not recorded'))]
            for lora in p.get('loras',[]):
                lines += ['- Image LoRA: '+text(lora.get('name','Not recorded'))+'. Source and terms: '+text(lora.get('civitai',{}).get('source_url','Not recorded; consult its provider.'))]
        lines += ['', 'Image-model terms are separate from the downstream geometry and texturing resources below. The structured record binds each originating image to its accepted revision and checksum.','']
    quad=c.production.get("quad_retopology") or {}
    if quad.get("requested_method"):
        names={"quadriflow":"QuadriFlow CPU","instant_meshes":"Instant Meshes CPU","cyber_cuda":"CyberRemesher NVIDIA CUDA",
               "topology_preserving":"Foundry topology-preserving subdivision"}
        used=", ".join(names.get(method,method) for method in quad.get("effective_methods",[]))
        lines += ["### Quad retopology","", "- Requested method: "+text(names.get(quad["requested_method"],quad["requested_method"]))+".",
                  "- Methods used on major parts: "+text(used or "No major parts needed remeshing")+".",""]
    turnaround=c.production.get("turnaround",{})
    if turnaround:
        lines += ["### Turnaround settings", "", "| Setting | Recorded value |", "|---|---|"]
        if c.production.get("category"):lines += ["| Asset category | "+text(c.production["category"])+" |"]
        for key,label in (("name","Image model"),("recipe","Prompt recipe"),("guidance","Instruction source"),
                          ("width","Sheet width (pixels)"),("height","Sheet height (pixels)"),
                          ("steps","Sampling steps"),("cfg","Guidance scale"),("seed","Seed"),
                          ("sampler","Sampler"),("scheduler","Scheduler")):
            if key in turnaround:lines += ["| "+label+" | "+fmt(turnaround[key])+" |"]
        lines += [""]
    if c.resources:
        lines+=["| Stage | Resource | Version | Source |","|---|---|---|---|"]
        for r in c.resources:
            url=r.get("source");source="[Project]("+quote(url,safe=":/._-#")+")" if url else "Not recorded"
            lines+=["| "+text(r.get("stage","Not recorded"))+" | "+text(r["name"])+" | "+fmt(r.get("version"))+" | "+source+" |"]
        lines += ["", "### Resource licenses", ""]
        for r in c.resources:
            url=r.get("license_url")
            source=" [License]("+quote(url,safe=":/._-#")+")" if url else ""
            lines += ["- **"+text(r["name"])+"** — "+text(r.get("license") or "Not recorded")+". "+text(r.get("license_summary") or "Consult the retained notices and resource source.")+source]
    else:lines+=["Production provenance was not supplied with these output files."]
    if c.warnings:lines+=["","**Documentation status**",""]+["- "+text(x) for x in c.warnings]
    lines+=["","## About "+text(c.project_identity.get("name") or "Mumblebox"),"",text(c.project_identity.get("description") or "")]
    for k,label in (("github_url","Project repository"),("homepage_url","Homepage"),("pinokio_url","Pinokio")):
        url=c.project_identity.get(k)
        if url:lines+=["",label+": ["+text(url)+"]("+quote(url,safe=":/._-#")+")"]
    terms=c.project_identity.get("terms");lines+=["","## Terms and notices",""]
    if terms:lines+=["Mumblebox terms: "+text(terms["path"])+"; version "+text(terms.get("version","not recorded"))+"."]
    else:lines+=["Mumblebox terms: not supplied for this export."]
    lines+=["","A finished-asset license has not been assigned by this packaging operation.",""]
    return "\n".join(lines)
