"""Run Foundry's automated release checks without starting the app or loading models."""
import argparse
import asyncio
import difflib
import hashlib
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from zipfile import ZipFile

import build_release


ROOT = build_release.ROOT
PACK = build_release.PACK


def run_checks():
    build_release.validate_text_encoding(build_release.inventory())
    build_release.validate_documented_version()

    launcher = ROOT / "scripts/pinokio/test_launcher.cjs"
    frontend = sorted((PACK / "foundry_tests").glob("test_*.mjs"))
    subprocess.run(["node", "--test", launcher, *frontend], cwd=ROOT, check=True)
    for directory, pattern in (
        ("scripts", "test_release.py"),
        ("scripts/pinokio", "test_*.py"),
        ("comfyui_asset_workshop/foundry_tests", "test_updates.py"),
        ("comfyui_asset_workshop/foundry_tests", "test_foundry_mcp_contract.py"),
        ("comfyui_asset_workshop/foundry_tests", "test_rigging*.py"),
    ):
        subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", directory, "-p", pattern],
            cwd=ROOT, check=True,
        )


def commit_for(ref):
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=ROOT, text=True,
    ).strip()


async def mcp_catalog(entry):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    # Reserve a loopback port without listening. The real stdio handshake
    # can list tools while Foundry's connection heartbeat has no app to reach.
    with socket.socket() as offline:
        offline.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{offline.getsockname()[1]}"
        params = StdioServerParameters(command=sys.executable,
            args=["-B", str(entry), "--comfy-url", url], cwd=str(entry.parent))
        async with asyncio.timeout(20):
            async with Client(params) as client:
                tools = (await client.list_tools()).tools
    if not tools:
        raise ValueError(f"MCP advertised no tools: {entry}")
    return {tool.name: tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in tools}


def check_mcp(base, catalog_file):
    manifest = json.loads((ROOT / "dependencies.json").read_text(encoding="utf-8-sig"))["mcp"]
    requirements = (PACK / "agent/requirements.txt").read_text(encoding="utf-8-sig").splitlines()
    sdk = manifest["sdk"]
    if f"mcp=={sdk}" not in requirements or version("mcp") != sdk:
        raise ValueError(f"Use MCP SDK {sdk} from the Foundry dependency manifest and agent requirements.")

    catalog = asyncio.run(mcp_catalog(ROOT / manifest["entry"]))
    print(f"MCP stdio discovery: {len(catalog)} tools.", flush=True)
    if catalog_file:
        catalog_file.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not base:
        return
    commit = commit_for(base)
    raw = subprocess.check_output(
        ["git", "archive", "--format=zip", commit, "dependencies.json", "comfyui_asset_workshop/agent"], cwd=ROOT,
    )
    with tempfile.TemporaryDirectory(prefix="foundry-mcp-base-") as directory, ZipFile(BytesIO(raw)) as snapshot:
        snapshot.extractall(directory)
        previous = json.loads(snapshot.read("dependencies.json").decode("utf-8-sig"))["mcp"]
        if previous["sdk"] != sdk:
            raise ValueError("The releases use different MCP SDKs. Compare their catalogs using each release's own SDK.")
        old_catalog = asyncio.run(mcp_catalog(Path(directory) / previous["entry"]))

    before = json.dumps(old_catalog, indent=2, sort_keys=True).splitlines()
    after = json.dumps(catalog, indent=2, sort_keys=True).splitlines()
    changes = list(difflib.unified_diff(before, after, fromfile=base, tofile="candidate", lineterm=""))
    if changes:
        print("\n".join(changes))
    else:
        print(f"MCP tool catalog matches {base}.")


def verify_archive(archive, ref):
    commit = commit_for(ref)
    with ZipFile(archive) as package:
        hashes = json.loads(package.read("SHA256SUMS.json"))
        names = package.namelist()
        if not isinstance(hashes, dict) or len(names) != len(set(names)) or set(names) != hashes.keys() | {"SHA256SUMS.json"}:
            raise ValueError("Release ZIP contains missing, unlisted or duplicate paths.")

        for autocrlf in ("true", "false"):
            raw = subprocess.check_output(
                ["git", "-c", f"core.autocrlf={autocrlf}", "archive", "--format=zip", commit], cwd=ROOT,
            )
            with ZipFile(BytesIO(raw)) as source:
                for name, digest in hashes.items():
                    payload = package.read(name)
                    if hashlib.sha256(payload).hexdigest() != digest or payload != source.read(name):
                        raise ValueError(f"Release ZIP differs from {commit} with core.autocrlf={autocrlf}: {name}")
                if autocrlf == "true":
                    with tempfile.TemporaryDirectory(prefix="foundry-release-source-") as directory:
                        source.extractall(directory)
                        root = Path(directory)
                        expected = {p.relative_to(root).as_posix() for p in build_release.inventory(root)}
                        if expected != hashes.keys():
                            raise ValueError("Release ZIP inventory differs from the builder's inventory for the commit.")
    with archive.open("rb") as payload:
        digest = hashlib.file_digest(payload, "sha256").hexdigest()
    print(f"Release ZIP: {len(hashes)} files match {commit} under both Git line-ending settings.")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Compare the MCP catalog against a previous public Git tag")
    parser.add_argument("--catalog", type=Path, help="Save the discovered tool catalog as JSON")
    parser.add_argument("--archive", type=Path, help="Optionally verify a built release ZIP")
    parser.add_argument("--ref", help="Commit or tag to verify against --archive")
    options = parser.parse_args()
    if bool(options.archive) != bool(options.ref):
        parser.error("--archive and --ref must be supplied together")
    try:
        check_mcp(options.base, options.catalog)
        run_checks()
        if options.archive:
            verify_archive(options.archive, options.ref)
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release checks failed: {error}\n")
    print("Automated release checks passed.")
