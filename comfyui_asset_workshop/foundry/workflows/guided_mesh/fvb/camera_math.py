"""Known centered perspective cameras in Blender/native projection Z-up space."""
import math
import copy
import numpy as np

A=np.array([[1,0,0],[0,0,-1],[0,1,0]],dtype=float)


def rig(bounds, include_top=False, azimuths=(45,135,225,315), elevation=20, fov=20, margin=1.05, views=None, yaw=0, size=1024, pitch=0, roll=0):
    low,high=np.asarray(bounds,dtype=float)
    extent=float(np.max(high-low))
    if not np.isfinite([*low,*high]).all() or extent<=0 or np.any(high<low):
        raise ValueError('Proxy must have finite nonzero bounds.')
    center=(high+low)/2
    angle=math.radians(yaw)
    p,r=map(math.radians,(pitch,roll))
    Rx=np.array([[1,0,0],[0,math.cos(p),-math.sin(p)],[0,math.sin(p),math.cos(p)]])
    Ry=np.array([[math.cos(r),0,math.sin(r)],[0,1,0],[-math.sin(r),0,math.cos(r)]])
    rotate=np.array([[math.cos(angle),-math.sin(angle),0],[math.sin(angle),math.cos(angle),0],[0,0,1]])@Ry@Rx@A
    # Fit the rotated bounding box to the native unit domain; rotation must not push it outside the reconstruction grid.
    import itertools
    corners=np.array(list(itertools.product(*zip(low,high))))
    rotated=(corners-center)@rotate.T
    scale=.99999/float(np.max(rotated.max(0)-rotated.min(0)))
    H=np.eye(4); H[:3,:3]=rotate*scale; H[:3,3]=-rotate@center*scale
    radius=float(np.linalg.norm((high-low)*.5)*scale)
    distance=radius/math.sin(math.radians(fov)/2)*margin
    names={45:'front_right',135:'rear_right',225:'rear_left',315:'front_left',0:'front',180:'back',90:'right',270:'left'}
    views=views or [dict(id=names.get(a%360,'view_'+str(i)),azimuth_deg=a,elevation_deg=elevation) for i,a in enumerate(azimuths)]
    views=list(views)
    if include_top and not any(v['id']=='top' for v in views):
        views.append(dict(id='top',azimuth_deg=0,elevation_deg=90))
    result=[]
    for index,v in enumerate(views):
        az,el=map(math.radians,(v['azimuth_deg'],v['elevation_deg']))
        eye=distance*np.array([-math.sin(az)*math.cos(el),-math.cos(az)*math.cos(el),math.sin(el)])
        back=eye/np.linalg.norm(eye)
        world_up=np.array([0,0,1]) if abs(back[2])<.99999 else np.array([0,1,0])
        right=np.cross(world_up,back); right/=np.linalg.norm(right)
        up=np.cross(back,right)
        C=np.eye(4); C[:3,:3]=np.stack([right,up,back],axis=1); C[:3,3]=eye
        rad=math.radians(fov); half=size/2; focal=half/math.tan(rad/2)
        camera=dict(schema='fvb.camera/1', id=v['id'], order=index, width=size,height=size,
            projection='perspective',azimuth_deg=v['azimuth_deg'],elevation_deg=v['elevation_deg'],roll_deg=0,
            fov_x_rad=rad,fov_y_rad=rad,fov_x_deg=fov,fov_y_deg=fov,sensor_width_mm=32,
            lens_mm=16/math.tan(rad/2),sensor_fit='HORIZONTAL',lens_shift=[0,0],pixel_aspect=[1,1],
            c2w=C.tolist(),w2c=np.linalg.inv(C).tolist(),K=[[focal,0,half],[0,focal,half],[0,0,1]],
            position=eye.tolist(),target=[0,0,0],near=.001,far=1000,mesh_scale=1,
            mesh_to_blender=H.tolist(),blender_to_mesh=np.linalg.inv(H).tolist(),
            image_transforms=[],calibration_status='requested_render',distance=distance,proxy_yaw_deg=yaw,
            proxy_pitch_deg=pitch,proxy_roll_deg=roll,
            world_frame='Z-up; front camera -Y; camera X right, Y up, -Z forward',
            pixel_convention='top-left origin, pixel centers as native Pixal projection',
            background='alpha or black; RGB premultiplied by alpha for conditioning')
        validate_camera(camera)
        result.append(camera)
    return result


def validate_camera(camera):
    C=np.asarray(camera['c2w'],dtype=float); W=np.asarray(camera['w2c'],dtype=float); K=np.asarray(camera['K'],dtype=float)
    if C.shape!=(4,4) or W.shape!=(4,4) or K.shape!=(3,3) or not all(np.isfinite(x).all() for x in (C,W,K)):
        raise ValueError('Camera matrices must be finite and correctly shaped.')
    R=C[:3,:3]
    if not np.allclose(C[3],[0,0,0,1],atol=1e-6) or not np.allclose(R.T@R,np.eye(3),atol=1e-5) or not np.isclose(np.linalg.det(R),1,atol=1e-5) or not np.allclose(W@C,np.eye(4),atol=1e-5):
        raise ValueError('Camera basis/inverse is inconsistent or not right-handed.')
    if camera['projection']!='perspective' or not isinstance(camera['width'],int) or camera['width']<=0 or camera['height']!=camera['width']:
        raise ValueError('Pixal views require centered square perspective cameras.')
    fov=float(camera['fov_x_rad'])
    if not math.isfinite(fov) or not 0<fov<math.pi:
        raise ValueError('Invalid horizontal field of view.')
    half=camera['width']/2; focal=half/math.tan(fov/2)
    if not np.allclose(K,[[focal,0,half],[0,focal,half],[0,0,1]],atol=1e-3):
        raise ValueError('Camera intrinsics do not match centered native projection.')
    if camera.get('mesh_scale')!=1 or camera.get('image_transforms'):
        raise ValueError('Reconstruction requires the recorded normalized full frame without image warps.')


def resize_camera(camera,size):
    """Uniform full-frame resize; camera pose/FOV and normalized object stay fixed."""
    validate_camera(camera)
    result=copy.deepcopy(camera); factor=size/camera['width']
    K=np.asarray(camera['K'],dtype=float); K[:2]*=factor
    result.update(width=size,height=size,K=K.tolist(),conditioning_resize={
        'from':[camera['width'],camera['height']],'to':[size,size],
        'pixel_transform':[[factor,0,0],[0,factor,0],[0,0,1]]})
    validate_camera(result)
    return result


def project(points,camera):
    p=np.c_[np.asarray(points),np.ones(len(points))]@np.asarray(camera['w2c']).T
    k=np.asarray(camera['K']); depth=-p[:,2]
    return np.stack([k[0,0]*p[:,0]/depth+k[0,2],-k[1,1]*p[:,1]/depth+k[1,2]],axis=1)


def canonical_anchor(cameras):
    """Rebase measured poses and their world together; retain a mesh-frame inverse."""
    if not cameras:raise ValueError('Choose at least one camera for the anchor frame.')
    for camera in cameras:validate_camera(camera)
    main=np.asarray(cameras[0]['c2w'],dtype=float)
    distance=float(np.linalg.norm(main[:3,3]))
    if distance<=0:raise ValueError('The anchor camera must orbit a nonzero distance from the origin.')
    front=np.eye(4);front[:3,:3]=A;front[:3,3]=[0,-distance,0]
    rotation_frame=front@np.linalg.inv(main)
    if not np.allclose(rotation_frame[:3,3],0,atol=1e-5):
        raise ValueError('Anchor conversion requires the measured cameras to look at the normalized origin.')
    rotation_frame[:3,3]=0
    # Fit the rotated unit cube; scale translations equally to retain projection.
    import itertools
    corners=np.array(list(itertools.product([-.5,.5],repeat=3)))
    rotated=corners@rotation_frame[:3,:3].T
    scale=min(1.,.99999/(2*float(np.abs(rotated).max())))
    transform=rotation_frame.copy();transform[:3,:]*=scale
    result=[]
    for camera in cameras:
        item=copy.deepcopy(camera);old=np.asarray(camera['c2w'],dtype=float)
        pose=np.eye(4);pose[:3,:3]=rotation_frame[:3,:3]@old[:3,:3]
        pose[:3,3]=(transform@np.r_[old[:3,3],1])[:3]
        item.update(c2w=pose.tolist(),w2c=np.linalg.inv(pose).tolist(),position=pose[:3,3].tolist(),
            distance=float(np.linalg.norm(pose[:3,3])),target=[0,0,0],
            conditioning_anchor_id=cameras[0]['id'],world_frame='Pixal canonical main-view Z-up')
        item['azimuth_deg']=math.degrees(math.atan2(-pose[0,3],-pose[1,3]))%360
        item['elevation_deg']=math.degrees(math.asin(pose[2,3]/item['distance']))
        validate_camera(item);result.append(item)
    axes=np.eye(4);axes[:3,:3]=A
    frame=dict(schema='fvb.reconstruction-frame/1',mode='canonical_anchor',anchor_id=cameras[0]['id'],
        world_to_conditioning=transform.tolist(),conditioning_to_world=np.linalg.inv(transform).tolist(),
        conditioning_mesh_to_world_mesh=(np.linalg.inv(axes)@np.linalg.inv(transform)@axes).tolist(),
        domain_scale=scale,domain_fit='conservative normalized unit-cube bounds',
        original_cameras=cameras,conditioning_cameras=result,
        note='Coordinate conversion preserves projection; generated-image calibration remains unverified.')
    return result,frame
