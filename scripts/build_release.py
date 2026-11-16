"""Build the public archive from an explicit inventory, without local user state."""
import argparse, hashlib, json, re, runpy, shutil, subprocess, tempfile, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/"comfyui_asset_workshop"
TOP=("README.md","CHANGELOG.md","INSTALL.md","THIRD-PARTY.md","LICENSE","NOTICE","dependencies.json","requirements-worker-windows.txt",
     "pinokio.js","pinokio.json","install.js","start.js","update.js","repair.js","icon.png")
DIRECTORIES=("agent","finishing","foundry","licenses","material_lab","pipeline_workers","skills","web","workflows")
EXTENSIONS={".py",".json",".js",".css",".svg",".png",".webp",".md",".txt",".html",".mg"}
IGNORED={".venv","__pycache__","node_modules",".git"}
TEXT_EXTENSIONS=EXTENSIONS-{".png",".webp"}
CYBER_PAYLOAD=Path("finishing/vendor/cyber-cuda")
CYBER_BINARY_FILES={"cyberremesh.exe","cudart64_12.dll","foundry-cuda.patch"}

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

def localized_readmes(root=ROOT):
    manifest = json.loads((root / PACK.name / "web/foundry/locales/manifest.json").read_text(encoding="utf-8-sig"))
    return [root / "docs" / f"README.{language['id']}.md" for language in manifest["languages"] if language["id"] != "en"]


def validate_documented_version(root=ROOT):
    pack = root / PACK.name
    version = runpy.run_path(str(pack / "foundry/__init__.py"))["VERSION"]
    installer = json.loads((root / "dependencies.json").read_text(encoding="utf-8-sig"))
    if installer["version"] != version:
        raise ValueError(f"The installer dependency manifest must use Foundry version {version}.")
    skill = pack / "skills/mumblebox-assets"
    documents = [root / "README.md", *localized_readmes(root), skill / "SKILL.md"]
    for document in documents:
        header = "\n".join(document.read_text(encoding="utf-8-sig").splitlines()[:12])
        displayed = re.findall(r"\b(\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?)\b", header)
        if displayed != [version]:
            raise ValueError(f"{document.relative_to(root)} must display Foundry version {version}.")
    compatibility = json.loads((skill / "compatibility.json").read_text(encoding="utf-8-sig"))
    if compatibility["reviewed_foundry_version"] != version:
        raise ValueError(f"Review the bundled skill for Foundry {version} and update its compatibility record.")


def inventory(root=ROOT):
    pack = root / PACK.name
    files = [root / name for name in TOP] + localized_readmes(root)
    files+=list((root/"licenses").glob("*.txt"))
    files.extend(pack/CYBER_PAYLOAD/name for name in CYBER_BINARY_FILES)
    files+=[root/"docs"/name for name in ("LOCALIZATION.md","LOCALIZATION-VALIDATION.md","AGENT-SETUP.md","RELEASE-VALIDATION.md","PINOKIO.md","HAIR-WORKFLOW.md","SPLAT-SOLID.md","LOCAL-UPDATE-VALIDATION.md","GROUNDING-VALIDATION.md")]
    demo = root / "docs/demos/2026-11-ray-gun"
    files.extend(demo / name for name in ("README.md", "provenance.json", "red-comet-poster.jpg"))
    files+=[root/"scripts"/name for name in ("install_foundry.py","install_hairdeck.py","probe_hairdeck.py","probe_hair_color.py","build_release.py","requirements-hair-windows.txt")]
    files+=[root/"scripts"/"pinokio"/name for name in ("bootstrap.py","runtime.py","maintenance.py","connect_agent.py","hi3d_entry.py")]
    files+=[p for p in pack.iterdir() if p.is_file() and p.suffix in EXTENSIONS and p.name not in ("README.md","PIPELINE.md")]
    for directory in DIRECTORIES:
        for path in (pack/directory).rglob("*"):
            rel=path.relative_to(pack)
            if not path.is_file() or path.suffix not in EXTENSIONS or any(part in IGNORED for part in rel.parts):continue
            if directory=="workflows" and path.name!="Mumblebox 3D Asset Foundry.json":continue
            if directory=="web" and path.name in ("logo.png","logo-dark.png","logo-light.png","logo-dark.svg","logo-light.svg"):continue
            files.append(path)
    return sorted(set(files))

def build(destination, *, ref="HEAD", repository=ROOT):
    destination=Path(destination).resolve()
    archive=Path(str(destination)+".zip")
    if destination.exists() or archive.exists():
        raise FileExistsError("Choose an unused release staging directory")
    if ref is None:
        return build_inventory(destination, archive, repository)

    # Pinokio's updater compares with git archive. Use that same source rather
    # than a Windows checkout that may have different line endings.
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", ref+"^{commit}"],
        cwd=repository, text=True).strip()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".foundry-source-", dir=destination.parent) as folder:
        snapshot=Path(folder)/"git-source.zip"
        subprocess.run(["git", "archive", "--format=zip", "--output", str(snapshot), commit],
                       cwd=repository, check=True)
        source=Path(folder)/"tree"
        with zipfile.ZipFile(snapshot) as zipped:
            zipped.extractall(source)
        return build_inventory(destination, archive, source)

def build_inventory(destination, archive, root):
    files=inventory(root)
    validate_text_encoding(files)
    validate_documented_version(root)
    destination.mkdir(parents=True)
    hashes={}
    for source in files:
        relative=source.relative_to(root);target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        hashes[relative.as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    (destination/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file():output.write(path,path.relative_to(destination))
    with zipfile.ZipFile(archive) as check:
        if check.testzip():raise RuntimeError("Release archive CRC check failed")
    print(json.dumps({"archive":str(archive),"files":len(hashes),"bytes":archive.stat().st_size,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))
    return archive

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("destination",help="Unused staging directory")
    source=parser.add_mutually_exclusive_group()
    source.add_argument("--ref",default="HEAD",help="Git tag or commit to package (default: HEAD)")
    source.add_argument("--working-tree",action="store_true",help="Build an unpublished test candidate from local files")
    args=parser.parse_args()
    build(args.destination,ref=None if args.working_tree else args.ref)
