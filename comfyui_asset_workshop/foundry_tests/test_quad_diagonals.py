"""A quad's triangulation must not manufacture a nonmanifold edge."""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finishing.quad_contract import normalize_quad_diagonals


class QuadDiagonalTests(unittest.TestCase):
    def test_existing_polygon_edge_uses_the_other_quad_diagonal(self):
        polygons=[[0,1,2,3],[0,2,4]]
        normalized,rotations=normalize_quad_diagonals(polygons)
        self.assertEqual(polygons,[[0,1,2,3],[0,2,4]])
        self.assertEqual(rotations,1)
        self.assertEqual(normalized,[[1,2,3,0],[0,2,4]])
        edges=Counter()
        for p in normalized:
            for i in range(1,len(p)-1):
                tri=[p[0],p[i],p[i+1]]
                edges.update(tuple(sorted((tri[j],tri[(j+1)%3]))) for j in range(3))
        self.assertLessEqual(max(edges.values()),2)

    def test_separate_quads_cannot_reuse_the_same_diagonal(self):
        polygons = [[0, 1, 2, 3], [0, 4, 2, 5]]
        normalized, rotations = normalize_quad_diagonals(polygons)
        self.assertEqual(rotations, 1)
        self.assertEqual(normalized, [[0, 1, 2, 3], [4, 2, 5, 0]])

    def test_ambiguous_diagonals_still_fail(self):
        with self.assertRaisesRegex(ValueError,'no safe fixed diagonal'):
            normalize_quad_diagonals([[0,1,2,3],[0,2,4],[1,3,5]])

if __name__=='__main__':unittest.main()
