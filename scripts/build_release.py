"""Build the public archive from an explicit inventory, without local user state."""
import argparse, hashlib, json, shutil, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/"comfyui_asset_workshop"
TOP=("README.md","CHANGELOG.md","INSTALL.md","THIRD-PARTY.md","LICENSE","NOTICE","dependencies.json","requirements-worker-windows.txt",
     "pinokio.js","pinokio.json","install.js","start.js","update.js","repair.js","icon.png")
DIRECTORIES=("agent","finishing","foundry","licenses","material_lab","pipeline_workers","web","workflows")
EXTENSIONS={".py",".json",".js",".css",".svg",".png",".md",".txt",".html"}
IGNORED={".venv","__pycache__","node_modules",".git"}
TEXT_EXTENSIONS=EXTENSIONS-{".png"}

def validate_text_encoding(files):
    """Reject broken source text before it can enter a public package."""
    corrupt_sequences=("\ufffd", "\u00c2\u00b7", "\u00c2\u00a0", "\u00e2\u20ac", "\u00e2\x80", "\u00e2\u2013")
    for path in files:
        if path.suffix not in TEXT_EXTENSIONS:continue
        try:text=path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Release text must be UTF-8: {path}") from exc
        if any(sequence in text for sequence in corrupt_sequences):
            raise ValueError(f"Corrupted text encoding in release file: {path}")

def inventory():
    files=[ROOT/name for name in TOP]
    files+=list((ROOT/"licenses").glob("*.txt"))
    files+=[ROOT/"docs"/name for name in ("AGENT-SETUP.md","RELEASE-VALIDATION.md","PINOKIO.md","HAIR-WORKFLOW.md","SPLAT-SOLID.md")]
    files+=[ROOT/"scripts"/name for name in ("install_foundry.py","install_hairdeck.py","probe_hairdeck.py","probe_hair_color.py","build_release.py","requirements-hair-windows.txt")]
    files+=[ROOT/"scripts"/"pinokio"/name for name in ("bootstrap.py","runtime.py","maintenance.py","connect_agent.py","hi3d_entry.py")]
    files+=[p for p in PACK.iterdir() if p.is_file() and p.suffix in EXTENSIONS and p.name not in ("README.md","PIPELINE.md")]
    for directory in DIRECTORIES:
        for path in (PACK/directory).rglob("*"):
            rel=path.relative_to(PACK)
            if not path.is_file() or path.suffix not in EXTENSIONS or any(part in IGNORED for part in rel.parts):continue
            if directory=="workflows" and path.name!="Mumblebox 3D Asset Foundry.json":continue
            if directory=="web" and path.name in ("logo.png","logo-dark.png","logo-light.png","logo-dark.svg","logo-light.svg"):continue
            files.append(path)
    return sorted(set(files))

def build(destination):
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("Choose an unused release staging directory")
    files=inventory()
    validate_text_encoding(files)
    destination.mkdir(parents=True)
    hashes={}
    for source in files:
        relative=source.relative_to(ROOT);target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        hashes[relative.as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    (destination/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    archive=Path(str(destination)+".zip")
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file():output.write(path,path.relative_to(destination))
    with zipfile.ZipFile(archive) as check:
        if check.testzip():raise RuntimeError("Release archive CRC check failed")
    print(json.dumps({"archive":str(archive),"files":len(hashes),"bytes":archive.stat().st_size,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("destination",help="Unused staging directory")
    build(parser.parse_args().destination)
