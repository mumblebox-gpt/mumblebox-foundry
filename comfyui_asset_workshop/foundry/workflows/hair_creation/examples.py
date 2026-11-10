"""Share the bundled, credited HairDeck references between the wizard and MCP."""
import hashlib
import json
from pathlib import Path
from threading import Lock

from ...artifacts import owned_path


ROOT = Path(__file__).resolve().parents[3] / "web" / "foundry" / "hair" / "examples"
SOURCE = json.loads((ROOT / "SOURCE.json").read_text(encoding="utf-8-sig"))
EXAMPLES = {Path(name).stem: (name, digest) for name, digest in SOURCE["files"].items()}
WRITE_LOCK = Lock()


def catalog():
    return [
        {"id": ident, "label": f"Example {index}", "source": SOURCE["source"],
         "url": f"/mumblebox-foundry/v1/hair/examples/{ident}/file"}
        for index, ident in enumerate(EXAMPLES, start=1)
    ]


def example_file(ident):
    try:
        name, digest = EXAMPLES[ident]
    except KeyError:
        raise ValueError("Choose one of the bundled HairDeck examples.") from None
    return ROOT / name, digest


def use_example(input_root, ident):
    source, digest = example_file(ident)
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("The bundled HairDeck reference changed. Restore the installed example.")
    relative = Path("foundry-references") / f"hairdeck-{ident}-{digest[:12]}.png"
    target = owned_path(input_root, input_root / relative)
    with WRITE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("The previous example input changed and was preserved.")
        else:
            with target.open("xb") as output:
                output.write(data)
    return {"filename": relative.as_posix(), "example_id": ident, "sha256": digest}
