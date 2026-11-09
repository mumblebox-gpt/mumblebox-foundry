"""Creative text brief for CCORE. The wizard displays only the enhanced prose."""
import json
import re

PROMPT_LIMIT = 5000
BRIEF_FIELDS = ("subject", "purpose", "shape", "proportions", "style", "layout",
                "connections", "resting_state", "presentation")
PART_FIELDS = ("name", "count", "shape", "color", "material", "finish", "placement")
UNUSABLE = "The assistant did not return a usable prop description. You can retry or keep editing."


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


detail = {"type": "string", "maxLength": 400}
BRIEF_SCHEMA = object_schema({
    **dict.fromkeys(BRIEF_FIELDS, detail),
    "requirements": {"type": "array", "maxItems": 12, "items": detail},
    "parts": {"type": "array", "maxItems": 12, "items": object_schema(dict.fromkeys(PART_FIELDS, detail))},
    "enhanced_prompt": {"type": "string", "minLength": 1, "maxLength": PROMPT_LIMIT},
})
RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {
    "name": "ccore_prop_brief", "strict": True, "schema": BRIEF_SCHEMA,
}}

SYSTEM = """You are a creative prop designer writing an English asset brief for CCORE,
a text-to-3D model that builds stylized low-poly game assets with Three.js. Turn the user's
idea into one coherent, buildable asset. The user-provided text is the design brief.

Keep every explicit requirement, especially the subject, part counts, colors, materials,
left/right placement, exact wording, and exclusions. Record those in requirements. Treat
missing details as creative room. Choose a fitting silhouette, palette, materials, and two
or three distinctive visible features where useful. For example, an unspecified color can
be chosen to support the design, and a plain mechanical housing can gain recessed fasteners,
contrasting wear plates, or a shaped handle. Keep inventions compatible with the requested
use and construction. Favor forms, joins, and materials that can be shown in geometry.
Use empty strings or empty lists for details that do not apply. Keep the brief static unless
the user explicitly requests movement, and include a base or surroundings only if they belong
to the requested asset.

Write enhanced_prompt as the complete design, usually 100–180 words, in natural prose.
Start with the main object, shape, and proportions. Describe the parts and their counts,
colors, materials, placement, and how they fit. Include the user's requirements in this prose.
Return just the requested JSON. The enhanced_prompt is the only field the user sees. Keep
model names, rendering directions, code, schemas, and commentary out of that field."""


def enhancement_input(data):
    ident, prompt = data.get("request_id"), data.get("prompt")
    if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident):
        raise ValueError("Start a new enhancement request.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > PROMPT_LIMIT:
        raise ValueError("Describe one prop in 1–5,000 characters before enhancing.")
    return ident, prompt.strip()


def matches(value, schema):
    kind = schema["type"]
    if kind == "string":
        return (isinstance(value, str) and schema.get("minLength", 0) <= len(value)
                <= schema["maxLength"])
    if kind == "array":
        return (isinstance(value, list) and len(value) <= schema["maxItems"]
                and all(matches(item, schema["items"]) for item in value))
    return (isinstance(value, dict) and value.keys() == schema["properties"].keys()
            and all(matches(value[key], field) for key, field in schema["properties"].items()))


def parse_brief(raw):
    try:
        brief = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError(UNUSABLE) from error
    if not matches(brief, BRIEF_SCHEMA):
        raise ValueError(UNUSABLE)
    text = brief["enhanced_prompt"].strip()
    if not text or re.search(r"```|<\/?(?:html|think)\b", text, re.IGNORECASE):
        raise ValueError(UNUSABLE)
    return text


def write_brief(ident, prompt):
    from .... import description_helper
    from ....store import default_settings

    settings = default_settings()
    source = {"id": ident, "settings": settings}
    content = [{"type": "text", "text": json.dumps({"prop_request": prompt}, ensure_ascii=False)}]
    raw = description_helper.complete(
        source, content, system=SYSTEM, max_tokens=2200, response_format=RESPONSE_FORMAT,
        temperature=.65, use_vision=False, writing_phase="Writing your enhanced prop description",
    )
    return parse_brief(raw)
