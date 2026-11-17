"""Bounded source-space skin corrections shared by the editor and binder."""
import hashlib
import json
import math

MAX_STROKES = 128
MAX_POINTS = 24
MODES = ("paint", "add", "subtract", "smooth", "rigid")


def weight_key(state):
    edits = state.get("weight_edits", [])
    if not edits:
        return None
    return hashlib.sha256(json.dumps(edits, sort_keys=True, allow_nan=False).encode()).hexdigest()


def apply_target(weights, bone, target, locked, limit=4):
    """Set one influence while preserving exact locked weights and normalization."""
    fixed = {name: value for name, value in weights.items() if name in locked and value > 0}
    budget = max(0., 1-sum(fixed.values()))
    if bone in locked or budget < 1e-7:
        return weights
    others = sorted(((name, value) for name, value in weights.items()
                    if name not in locked and name != bone and value > 0), key=lambda entry: -entry[1])
    value = min(budget, max(0., target))
    slots = limit - len(fixed)
    if slots <= 0:
        return weights
    others = others[:slots-int(value > 1e-7)]
    if not others:
        value = budget
    result = {**fixed}
    if value > 1e-7:
        result[bone] = value
    leftover = budget-value
    if others and leftover > 1e-7:
        total = sum(weight for _, weight in others)
        result.update((name, weight * leftover/total) for name, weight in others)
    return result


def brush_value(mode, current, strength, target, neighborhood):
    if mode == "add":
        return current + strength
    if mode == "subtract":
        return current - strength
    if mode == "rigid":
        return 1.0
    goal = neighborhood if mode == "smooth" else target
    return current + strength*(goal-current)


def append_stroke(run, args, known, point_parser, geometry):
    bone = args.get("bone_id")
    mode = args.get("mode")
    points = args.get("points")
    if not isinstance(bone, str) or bone not in known or not known[bone].get("deform", True):
        raise ValueError("Choose a deform bone to edit its weights.")
    locked = run.get("weight_locks", [])
    if bone in locked:
        raise ValueError("Unlock this weight group before editing it.")
    if mode not in MODES or not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError("Choose a valid weight brush and 1 to 24 surface points.")
    output = run.get("output")
    if not output or output["skeleton"] != geometry:
        raise ValueError("Bind this skeleton before correcting weights.")
    low, high = run["bounds"]
    span = math.dist(low, high)
    values = {"radius": (1e-6, span*.20), "strength": (0, 1), "target": (0, 1)}
    normalized = {}
    for field, (minimum, maximum) in values.items():
        value = args.get(field, 1 if field == "target" else None)
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError("Choose a valid brush radius, strength and target.")
        normalized[field] = value
    edits = run.setdefault("weight_edits", [])
    if len(edits) >= MAX_STROKES:
        raise ValueError("The rig has reached its saved weight correction limit.")
    edits.append({"bone_id":bone, "mode":mode, "points":[point_parser(run["bounds"], p) for p in points],
                  "locked":list(locked), **normalized})
    return {bone}
