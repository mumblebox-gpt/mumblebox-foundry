"""Verify guided topology, mirror persistence and independent digit editing."""
import unittest
import test_rigging

from foundry.workflows.rigging.parts import layout


class PartsTests(unittest.TestCase):
    def test_bird_and_bat_have_distinct_branch_roles(self):
        args = ([0,0,0],[1,0,0],3,[0,.35,0])
        bird = layout("bird_wing",*args)
        bat = layout("bat_wing",*args)
        self.assertEqual(len(bird),7)
        self.assertEqual(len(bat),15)
        self.assertEqual({b["role"] for b in bird},{"wing","feather"})
        self.assertEqual({b["role"] for b in bat},{"wing","wing_digit"})

    def test_add_hand_prevents_duplicate_and_mirrors_without_mutating_original_geometry(self):
        fixture=test_rigging.RiggingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service=fixture.service
        run=service.create(fixture.id, service.sources(fixture.id)[0]["id"])
        args={"parent_id":"wrist.L","part":"hand","tip":[.95,1.05,.06],"segments":3,"width_point":[.92,.94,.13]}
        loaded,_=service.command(run["id"],0,"a"*32,"add_part",args)
        bones=loaded["skeleton"]["bones"]
        digits=[b for b in bones if b.get("role")=="finger"]
        self.assertEqual(len(digits),15)
        self.assertEqual(len({b["anatomical_name"] for b in digits}),5)
        root=loaded["selected_joint"]
        with self.assertRaisesRegex(ValueError,"already has"):
            service.command(run["id"],1,"b"*32,"add_part",args)
        mirrored,_=service.command(run["id"],1,"c"*32,"mirror_chain",{"bone_id":root})
        written={b["id"]:b for b in service.get(run["id"])["skeleton"]["bones"]}
        self.assertEqual(len(written),len(bones)+16)
        for b in digits:
            partner=written[written[b["id"]]["mirror_id"]]
            self.assertEqual(partner["head"],[-b["head"][0],*b["head"][1:]])
            self.assertEqual(written[b["id"]]["head"],b["head"])
        claw,_=service.command(run["id"],2,"d"*32,"move",{"joint":digits[0]["id"]+"/tip","point":[.94,1.01,.03]})
        moved={b["id"]:b for b in claw["skeleton"]["bones"]}
        self.assertEqual(moved[digits[0]["id"]]["tail"],[.94,1.01,.03])
        self.assertEqual(moved[digits[-1]["id"]]["tail"],digits[-1]["tail"])
        self.assertEqual(mirrored["rig_revision"],2)
