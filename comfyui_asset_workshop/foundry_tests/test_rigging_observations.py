"""A saved camera can only describe the same visible asset and revisions."""
import unittest

import test_rigging
from foundry.workflows.rigging.observations import ObservationStore


class ObservationTests(unittest.TestCase):
    def test_stale_view_and_browser_cannot_reuse_capture(self):
        now = [0]
        store = ObservationStore(clock=lambda: now[0])
        identity = {"run_id": "rig", "rig_revision": 3, "source_sha256": "source", "pose": "rest"}
        capture = store.put("browser", identity)
        self.assertEqual(store.get("browser", capture, identity)["rig_revision"], 3)
        for browser, state in (("other", identity), ("browser", {**identity, "rig_revision": 4}),
                               ("browser", {**identity, "pose": "elbow"})):
            with self.assertRaisesRegex(ValueError, "Capture"):
                store.get(browser, capture, state)
        now[0] = 120
        with self.assertRaisesRegex(ValueError, "Capture"):
            store.get("browser", capture, identity)

    def test_capture_cache_is_bounded(self):
        store = ObservationStore()
        identity = {"run_id": "rig", "rig_revision": 3}
        captures = [store.put("browser", identity) for _ in range(17)]
        with self.assertRaisesRegex(ValueError, "Capture"):
            store.get("browser", captures[0], identity)
        self.assertEqual(store.get("browser", captures[1], identity)["capture_id"], captures[1])
