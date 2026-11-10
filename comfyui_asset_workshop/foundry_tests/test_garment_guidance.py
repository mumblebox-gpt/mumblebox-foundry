"""Focused checks for Windows tensor replacements of the author's matching kernels."""
import sys
from pathlib import Path
import unittest

import torch

sys.path.insert(0, str(Path(__file__).parents[1] / 'foundry/workflows/garment_particles/workers'))
from matching import emd, one_way_chamfer
from guidance import blend


class GarmentGuidanceTests(unittest.TestCase):
    def test_identical_point_sets_are_zero_cost(self):
        points = torch.tensor([[0., 0., 0.], [1., 0., 0.]])
        self.assertAlmostEqual(emd(points, points.flip(0)).item(), 0.0, places=6)

    def test_emd_has_gradient_toward_target(self):
        points = torch.tensor([[0., 0., 0.], [1., 0., 0.]], requires_grad=True)
        target = points.detach() + torch.tensor([0., .25, 0.])
        emd(points, target).backward()
        self.assertTrue(torch.isfinite(points.grad).all())
        self.assertTrue((points.grad[:, 1] < 0).all())

    def test_completion_only_requires_the_given_subset(self):
        points = torch.tensor([[0., 0., 0.], [1., 0., 0.]])
        self.assertAlmostEqual(one_way_chamfer(points, points[:1]).item(), 0.0)

    def test_interpolation_matches_points_and_interpolates_count(self):
        first = torch.tensor([[[1., 0., 0.], [0., 1., 0.]]])
        second = torch.tensor([[[0., 1., 0.], [1., 0., 0.], [-1., 0., 0.], [0., -1., 0.]]])
        trajectory = lambda value: torch.stack([value, value]).numpy()
        midpoint = blend(trajectory, first, second, .5)
        self.assertEqual(tuple(midpoint.shape), (1, 3, 3))
        torch.testing.assert_close(midpoint[:, :2], first)
        torch.testing.assert_close(blend(trajectory, first, second, 1.), second)

