"""Bounded camera evidence tied to the scene the wizard actually showed."""
from copy import deepcopy
import time
from uuid import uuid4

from .document import surface_anchor
from .geometry import numbers
from .sessions import skeleton_key


CAPTURE_TTL = 120
PER_BROWSER = 16
TOTAL_CAPTURES = 64


def scene_identity(run):
    output = run.get("output")
    if output and (output["skeleton"] != skeleton_key(run) or output.get("file") != "rig.glb"):
        output = None
    bound = (run["pose"] != "rest" or run["step"] == "review") and output
    return {"run_id": run["id"], "revision": run["revision"], "rig_revision": run["rig_revision"],
            "view_revision": run["view_revision"], "source_sha256": run["source"]["sha256"],
            "geometry_key": run["source"]["sha256"], "binding_key": bound["binding"] if bound else None,
            "pose": run["pose"], "pose_key": run.get("joint_pose") or run["pose"]}


class ObservationStore:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.captures = {}

    def put(self, browser_id, observation):
        now = self.clock()
        for key, (_, deadline, _) in list(self.captures.items()):
            if deadline <= now:
                del self.captures[key]
        own = [key for key, (browser, _, _) in self.captures.items() if browser == browser_id]
        if len(own) >= PER_BROWSER:
            del self.captures[own[0]]
        if len(self.captures) >= TOTAL_CAPTURES:
            del self.captures[next(iter(self.captures))]
        capture_id = uuid4().hex
        record = {"schema": "foundry.spatial.v1", "capture_id": capture_id,
                  "created_at": time.time(), **deepcopy(observation)}
        self.captures[capture_id] = (browser_id, now + CAPTURE_TTL, record)
        return capture_id

    def get(self, browser_id, capture_id, identity):
        entry = self.captures.get(capture_id)
        if entry:
            owner, deadline, record = entry
            if owner == browser_id and deadline > self.clock() and all(record.get(k) == v for k, v in identity.items()):
                return deepcopy(record)
        raise ValueError("Capture the current rig again before using that observation.")


def normalized_pixels(pixels):
    if not isinstance(pixels, list) or not 1 <= len(pixels) <= 16:
        raise ValueError("Probe one to sixteen locations in the captured image.")
    result = [numbers(pixel, 2) for pixel in pixels]
    if any(not 0 <= value <= 1 for pixel in result for value in pixel):
        raise ValueError("Use image coordinates between zero and one.")
    return result


def probe_results(data, pixels):
    if not isinstance(data, list) or len(data) != len(pixels):
        raise ValueError("The wizard did not return every requested depth probe.")
    probes = []
    for sample, pixel in zip(data, pixels):
        hits = sample.get("hits")
        if sample.get("pixel") != pixel or not isinstance(hits, list) or len(hits) > 64:
            raise ValueError("The wizard returned an invalid depth probe.")
        verified = []
        for hit in hits:
            distance = numbers([hit.get("distance")], 1)[0]
            if distance < 0 or verified and distance < verified[-1]["distance"] - 1e-7:
                raise ValueError("The depth probe distances were not ordered.")
            verified.append({**surface_anchor(hit), "distance": distance, "position": numbers(hit.get("position"), 3),
                             "normal": numbers(hit.get("normal"), 3), "anchorable": hit.get("anchorable") is True})
        spans = sample.get("candidate_spans")
        reasons = sample.get("ambiguous_reasons")
        if (not isinstance(spans, list) or len(spans) > 1 or not isinstance(reasons, list)
                or len(reasons) > 8 or any(not isinstance(reason, str) or len(reason) > 80 for reason in reasons)):
            raise ValueError("The depth probe interpretation was invalid.")
        checked_spans = []
        for span in spans:
            if span.get("near") != 0 or span.get("far") != 1 or len(verified) != 2:
                raise ValueError("A suggested span requires two reviewed surface hits.")
            midpoint = [(a+b)/2 for a,b in zip(verified[0]["position"],verified[1]["position"])]
            checked_spans.append({"near": 0, "far": 1, "midpoint": midpoint})
        topology = sample.get("topology_status")
        if topology not in ("unknown","closed_edges","open_edges","overlapping_or_inconsistent"):
            raise ValueError("Unknown mesh topology result.")
        probes.append({"pixel": pixel, "hits": verified, "candidate_spans": checked_spans,
                       "topology_status": topology, "ambiguity": reasons, "truncated": sample.get("truncated") is True})
    return probes
