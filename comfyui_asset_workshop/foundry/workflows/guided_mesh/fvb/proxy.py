"""Explicit closed-box pose policy; no per-asset angles or display-only geometry."""
import numpy as np


def upright_box_frame(vertices):
    import trimesh
    vertices=np.asarray(vertices,dtype=np.float64)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices)<4 or not np.isfinite(vertices).all():
        raise ValueError('Proxy orientation needs finite 3D vertices.')
    if np.any(np.ptp(vertices,axis=0)<1e-8):raise ValueError('Degenerate proxy has no closed-box frame.')
    rng=np.random.default_rng(42)
    sample=vertices if len(vertices)<=50000 else vertices[rng.choice(len(vertices),50000,replace=False)]
    try:box,extents=trimesh.bounds.oriented_bounds(sample,angle_digits=1)
    except Exception as error:raise ValueError('Could not estimate a closed-box proxy frame.') from error
    axes=box[:3,:3]
    up_index=int(np.argmax(np.abs(axes[:,1])))
    width_index=max((i for i in range(3) if i!=up_index),key=lambda i:extents[i])
    up=axes[up_index].copy();right=axes[width_index].copy()
    if up[1]<0:up=-up
    if right[0]<0:right=-right
    front=np.cross(right,up);front/=np.linalg.norm(front)
    R=np.stack([right,up,front])
    moved=vertices@R.T;low,high=moved.min(0),moved.max(0)
    scale=.96/float((high-low).max())
    matrix=np.eye(4);matrix[:3,:3]=R*scale;matrix[:3,3]=-(low+high)*.5*scale
    report=dict(policy='upright_solid_box',method='trimesh oriented bounds; deterministic <=50000 vertices',
        orientation_assumption='Closed box-like prop, up nearest generated +Y; widest horizontal extent is width; front sign nearest generated +Z.',
        sample_seed=42,sample_count=len(sample),box_extents=extents.tolist(),matrix=matrix.tolist(),uniform_scale=scale,
        quality_limit='This estimates pose and normalizes uniformly. It does not straighten warped panels or prove semantic front.')
    return matrix,report
