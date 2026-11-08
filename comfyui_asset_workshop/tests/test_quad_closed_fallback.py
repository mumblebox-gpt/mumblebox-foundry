"""Closed-input fallback must keep topology and never cap intended openings."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finishing'))
import trimesh
from quad_worker import topology_preserving_quads,stats
class QuadFallback(unittest.TestCase):
    def test_closed_mesh_keeps_all_quads_and_watertight_topology(self):
        source=trimesh.creation.icosphere(subdivisions=3)
        v,f=topology_preserving_quads(source,600)
        checks=stats(v,f)
        self.assertTrue(checks['watertight']);self.assertTrue(checks['winding_consistent'])
        self.assertEqual(checks['boundary_edges'],0);self.assertEqual(checks['nonmanifold_edges'],0)
        self.assertEqual(checks['degenerate_triangles'],0);self.assertEqual(checks['quads'],len(f))
        self.assertLessEqual(abs(len(f)-600),150)
    def test_open_source_is_not_filled_by_fallback(self):
        source=trimesh.creation.box();source.update_faces([0,1,2,3,4,5])
        with self.assertRaises(ValueError):topology_preserving_quads(source,100)
if __name__=='__main__':unittest.main()
