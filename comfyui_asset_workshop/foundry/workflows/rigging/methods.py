"""Settings shared by the wizard, agent, and their fit and bind operations."""
import math

FIT_FIELDS = {
    "num_beams": {"min": 1, "max": 20, "step": 1, "default": 10},
    "top_k": {"min": 0, "max": 100, "step": 1, "default": 5},
    "top_p": {"min": 0.05, "max": 1.0, "step": 0.01, "default": 0.95},
    "temperature": {"min": 0.1, "max": 2.0, "step": 0.05, "default": 1.0},
    "repetition_penalty": {"min": 1.0, "max": 3.0, "step": 0.05, "default": 2.0},
    "seed": {"min": 0, "max": 2**31-1, "step": 1, "default": 31415},
}
BIND_FIELDS = {"proxy_resolution": {"min": 64, "max": 160, "step": 1, "default": 110}}
FIT_PRESETS = {"quick": {"num_beams": 4}, "standard": {}}
BIND_PRESETS = {"quick": {"proxy_resolution": 80}, "standard": {}, "fine": {"proxy_resolution": 150}}


def resolve(presets, fields, preset, custom):
    if not isinstance(custom, dict) or set(custom) - fields.keys():
        raise ValueError("Use the controls listed for this rigging method.")
    if preset == "custom":
        overrides = custom
    elif isinstance(preset, str) and preset in presets and not custom:
        overrides = presets[preset]
    else:
        raise ValueError("Choose a supported preset or select Custom to change its settings.")
    values = {key: spec["default"] for key, spec in fields.items()}
    for key, value in overrides.items():
        spec = fields[key]
        integer = type(spec["default"]) is int
        if (type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value)
                or not spec["min"] <= value <= spec["max"]):
            raise ValueError(f"Set {key} between {spec['min']} and {spec['max']}.")
        values[key] = value
    return values


def fit_settings(preset, custom):
    return resolve(FIT_PRESETS, FIT_FIELDS, preset, custom)


def bind_settings(preset, custom):
    return resolve(BIND_PRESETS, BIND_FIELDS, preset, custom)


def capabilities():
    return {"local_ai": {"fields": FIT_FIELDS, "presets": {key: fit_settings(key,{}) for key in FIT_PRESETS}},
            "binding": {"fields": BIND_FIELDS, "presets": {key: bind_settings(key,{}) for key in BIND_PRESETS}}}
