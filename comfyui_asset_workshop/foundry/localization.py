"""Catalog ownership and message resolution shared by the browser and package writers."""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "foundry" / "locales"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8-sig"))
SUPPORTED_LOCALES = tuple(item["id"] for item in MANIFEST["languages"])
DOMAINS = {name: ROOT / relative for name, relative in MANIFEST["domains"].items()}
PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


def locale_name(value):
    return value if value in SUPPORTED_LOCALES else "en"


@lru_cache(maxsize=4)
def catalog(locale="en"):
    locale = locale_name(locale)
    messages = {}
    for domain, directory in DOMAINS.items():
        source = directory / "en.json"
        if not source.is_file():
            continue
        english = json.loads(source.read_text(encoding="utf-8-sig"))
        target = directory / (locale + ".json")
        translated = json.loads(target.read_text(encoding="utf-8-sig")) if target.is_file() else {}
        if set(translated) - set(english):
            raise ValueError(f"Unknown translation keys in {target}")
        for key, text in english.items():
            if not isinstance(text, str):
                raise ValueError(f"Message {domain}.{key} must be text")
            value = translated.get(key, text)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Empty translation for {domain}.{key}")
            if set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(value)):
                raise ValueError(f"Translation parameters differ for {domain}.{key}")
            messages[domain + "." + key] = value
    return messages


def translate(key, values=None, locale="en"):
    text = catalog(locale).get(key, catalog("en").get(key, key))
    values = values or {}
    missing = set(PLACEHOLDER.findall(text)) - set(values)
    if missing:
        raise ValueError(f"Missing translation parameters for {key}: {sorted(missing)}")
    return PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), text)


def message(key, **values):
    """Stable wire representation. English diagnostics and machine fields stay intact."""
    return {"key": key, "values": values}


@lru_cache(maxsize=1)
def _source_index():
    exact = {}
    patterns = []
    for key, source in catalog("en").items():
        if key.startswith("ccore.preset_"):
            continue
        names = PLACEHOLDER.findall(source)
        if not names:
            exact.setdefault(source, key)
            continue
        if not re.search(r"[A-Za-z]", PLACEHOLDER.sub("", source)):
            continue
        pieces = PLACEHOLDER.split(source)
        expression = "".join("(.*?)" if index % 2 else re.escape(piece)
                             for index, piece in enumerate(pieces))
        patterns.append((key, names, re.compile("^" + expression + "$", re.DOTALL)))
    return exact, patterns


def source_message(source):
    """Identify known human messages, including text from older saved runs."""
    if not isinstance(source, str) or len(source) > 8192:
        return None
    exact, patterns = _source_index()
    if source in exact:
        return message(exact[source])
    for key, names, pattern in patterns:
        match = pattern.fullmatch(source)
        if match:
            return message(key, **dict(zip(names, match.groups())))
    return None


def translate_source(source, locale="en"):
    token = source_message(source)
    return translate(token["key"], token["values"], locale) if token else source


def interface_locale():
    """Ask the preference owner. Independent package tools default to English."""
    try:
        import folder_paths
    except ImportError:
        return "en"
    if not hasattr(folder_paths, "get_user_directory"):
        return "en"
    from .preferences import Preferences
    return Preferences(Path(folder_paths.get_user_directory()) / "mumblebox-foundry" / "preferences.json").read()["language"]
