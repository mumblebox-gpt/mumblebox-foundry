import unittest,sys,tempfile
from pathlib import Path
import numpy as np,trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finishing.grounding import plan_grounding,validate_frame,ground_glb,blender_frame
class Grounding(unittest.TestCase):
 def model(self):
  m=trimesh.creation.box([2,.8,2]);m.apply_translation([0,.9,0])
  for x in (-.8,.8):
   for z in (-.8,.8):
    leg=trimesh.creation.box([.3,.5,.3]);leg.apply_translation([x,.25,z]);m+=leg
  return m
 def test_tilted_feet_level_without_deformation(self):
  m=self.model();m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(14),[1,0,0]));r=plan_grounding(m.vertices,m.faces);T=validate_frame(r);v=trimesh.transform_points(m.vertices,T)
  self.assertTrue(np.allclose(T[:3,:3]@np.array([1.,0.,0.]),[1,0,0],atol=1e-6),'Pure pitch correction must not introduce yaw')
  self.assertAlmostEqual(v[:,1].min(),0,places=10);self.assertAlmostEqual(r['correction_degrees'],14,places=6)
  self.assertTrue(np.allclose(np.linalg.norm(np.diff(v,axis=0),axis=1),np.linalg.norm(np.diff(m.vertices,axis=0),axis=1)))
  for x in (-1,1):
   for z in (-1,1):self.assertAlmostEqual(v[(v[:,0]*x>0)&(v[:,2]*z>0),1].min(),0,places=8)
 def test_modes_and_no_flip(self):
  m=self.model();r=plan_grounding(m.vertices,m.faces);self.assertAlmostEqual(r['correction_degrees'],0,places=7)
  self.assertTrue(np.array_equal(validate_frame(plan_grounding(m.vertices,m.faces,'original')),np.eye(4)))
  r=plan_grounding(m.vertices+3,m.faces,'place');self.assertTrue(np.array_equal(validate_frame(r)[:3,:3],np.eye(3)))
  m.apply_transform(trimesh.transformations.rotation_matrix(.6,[1,0,0]));r=plan_grounding(m.vertices,m.faces,max_tilt=10);self.assertEqual(r['applied'],'place');self.assertTrue(r['warning'])
 def test_glb_matches_blender_frame_and_preserves_topology(self):
  m=self.model();m.apply_transform(trimesh.transformations.rotation_matrix(.2,[1,0,0]));T=validate_frame(plan_grounding(m.vertices,m.faces))
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.glb';b=Path(d)/'b.glb';m.export(a);ground_glb(a,b,T);out=trimesh.load(b,force='mesh',process=False)
   self.assertEqual(len(out.faces),len(m.faces));self.assertTrue(np.allclose(out.vertices,trimesh.transform_points(m.vertices,T),atol=1e-6))
  C=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],float)
  self.assertTrue(np.allclose(trimesh.transform_points(trimesh.transform_points(m.vertices,C),blender_frame(T)),trimesh.transform_points(trimesh.transform_points(m.vertices,T),C)))
 def test_invalid_input(self):
  with self.assertRaises(ValueError):plan_grounding(np.zeros((4,3)),np.array([[0,1,2]]))
  with self.assertRaises(ValueError):validate_frame({'matrix_y_up':(np.eye(4)*2).tolist(),'mode':'level'})
if __name__=='__main__':unittest.main()
