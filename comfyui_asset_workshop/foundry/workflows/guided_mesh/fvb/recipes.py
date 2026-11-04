"""Complete native processing graph and checkpoint-separated stage compiler."""
import copy
import json
from pathlib import Path
from .contracts import defaults, sheet_defaults, view_records, selected_views, effective_reference, effective_image_key
from .prompts import concept, enhancement, sheet_enhancement, repair_prompt

ROOT=Path(__file__).resolve().parents[1]
MODELS=json.loads((ROOT/'sources/models.lock.json').read_text(encoding='utf-8-sig'))['models']


def model(key):
    return MODELS[key]['name']


def ancestor(graph,endpoints):
    output={}; visiting=set()
    def visit(ident):
        ident=str(ident)
        if ident in visiting:
            raise ValueError('Cycle at node '+ident)
        if ident in output:
            return
        if ident not in graph:
            raise ValueError('Missing node '+ident)
        visiting.add(ident)
        for value in graph[ident].get('inputs',{}).values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and isinstance(value[1],int):
                visit(value[0])
        output[ident]=copy.deepcopy(graph[ident]); visiting.remove(ident)
    for ident in endpoints:
        visit(ident)
    return output


def graph_issues(graph):
    try:
        ancestor(graph,list(graph))
        return []
    except ValueError as error:
        return [str(error)]


def remap(graph,offset):
    def walk(value):
        if isinstance(value,list):
            if len(value)==2 and isinstance(value[0],str) and value[0] in graph and isinstance(value[1],int):
                return [str(int(value[0])+offset),value[1]]
            return [walk(v) for v in value]
        if isinstance(value,dict):
            return {k:walk(v) for k,v in value.items()}
        return value
    return {str(int(k)+offset):walk(v) for k,v in graph.items()}


def canonical_api(spec=None):
    s={**defaults(),**(spec or {})}; job=s['job_id']; graph={}
    def add(ident,kind,stage,title=None,**inputs):
        graph[str(ident)]=dict(class_type=kind,inputs=inputs,_meta=dict(title=title or kind,fvb_stage=stage))
        return [str(ident),0]
    def load(ident,key,stage):
        return add(ident,'G3D_LoadImage',stage,key,job_id=job,artifact_key=key)
    def save(ident,image,key,stage):
        return add(ident,'G3D_SaveImage',stage,key,image=image,job_id=job,artifact_key=key)
    def decode(ident,samples,vae,stage):
        return add(ident,'VAEDecodeTiled',stage,samples=samples,vae=vae,tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8) if s['tiled_vae'] else add(ident,'VAEDecode',stage,samples=samples,vae=vae)
    original=load(900,'original','concept')
    appearance=add(902,'G3D_ResizeReference','concept','Original appearance — preserve aspect',image=original,size=1024)
    save(903,appearance,'appearance','concept')
    qmodel=add(1551,'UNETLoader','concept',unet_name=model('qwen21'),weight_dtype='default')
    clip=add(1553,'CLIPLoader','concept',clip_name=model('qwen21_clip'),type='qwen_image',device='default')
    vae=add(1554,'VAELoader','concept',vae_name=model('qwen21_vae'))
    cache=add(1569,'QwenImage21Cache','concept',model=qmodel,device=s['cache_device'],dtype=s['cache_dtype'])
    budget=add(1570,'AW_ModelBudget','concept',model=cache,extra_gb=s['extra_vram_headroom_gb'])
    cond=add(1574,'TextEncodeQwenImage21','concept','UNCHANGED Foundry turnaround + reference notes',clip=clip,vae=vae,prompt=concept(s),negative_prompt='',resolution=0,**{'images.image_1':appearance})
    latent=add(1556,'EmptyLatentImage','concept',width=4096,height=1024,batch_size=1)
    sampled=add(1558,'KSampler','concept',model=budget,positive=cond,negative=['1574',1],latent_image=latent,
        seed=s['turnaround_seed'],steps=s['turnaround_steps'],cfg=s['turnaround_cfg'],sampler_name='euler',scheduler='simple',denoise=1.0)
    sheet=decode(1557,sampled,vae,'concept')
    save(1580,sheet,'concept:sheet','concept')
    for i,side in enumerate(('front','left','back','right')):
        crop=add(1590+i*2,'ImageCrop','concept',side+' concept panel',image=sheet,width=1024,height=1024,x=i*1024,y=0)
        save(1591+i*2,crop,'concept:'+side,'concept')

    # Preserve the existing Pixal/TRELLIS sampling ancestry; cut it at conditioning.
    baseline=json.loads((ROOT/'sources/foundry-template.api.json').read_text(encoding='utf-8-sig'))
    baseline['324']=dict(class_type='G3D_PixalViews',inputs={'clip_vision_model':['15',0],'camera_manifest':['7710',0]},_meta={'title':'Actual Blender matrices → Pixal projection'})
    if s.get('camera_convention')=='canonical_anchor':baseline['324']['inputs']['frame_mode']='canonical_anchor'
    baseline['7710']=dict(class_type='G3D_ReadCameras',inputs={'job_id':job,'selected_only':True,
        'source':'enhanced' if s['enhancement_mode']=='sheet' else 'render'})
    for i,v in enumerate(selected_views(s)):
        ident=str(7720+i)
        baseline[ident]=dict(class_type='G3D_LoadImage',inputs={'job_id':job,'artifact_key':effective_image_key(s,v['id'])})
        baseline['324']['inputs']['view_'+str(i)]=[ident,0]
    shape=ancestor(baseline,['92'])
    for ident,node in shape.items():
        node['_meta']={'title':node['class_type'],'fvb_stage':'reconstruct'}
        if 'filename_prefix' in node['inputs']:
            node['inputs']['filename_prefix']='FoundryViewBridge/'+job+'/'+ident
    shape['94']['inputs']['target_resolution']=s['reconstruction_resolution']
    for ident,seed,steps,scheduler in [('3',s['reconstruction_seed']+14,s['structure_steps'],'normal'),('18',s['reconstruction_seed'],s['shape_steps'],'normal'),('23',s['reconstruction_seed'],s['upscale_steps'],'simple')]:
        shape[ident]['inputs'].update(seed=seed,steps=steps,cfg=s['mesh_cfg'],scheduler=scheduler)
    graph.update(shape)
    for ident,source in [(7801,'108'),(7802,'126')]:
        add(ident,'AW_ModelBudget','reconstruct',model=[source,0],extra_gb=s['extra_vram_headroom_gb'])
    graph['3']['inputs']['model']=['7801',0]
    for ident in ('18','23'):
        graph[ident]['inputs']['model']=['7802',0]
    reconstructed=['92',0]
    if s.get('camera_convention')=='canonical_anchor':
        reconstructed=add(7899,'G3D_RestoreReconstructionFrame','reconstruct','Restore measured mesh frame after canonical-anchor generation',mesh=reconstructed,camera_manifest=['7710',0],job_id=job)
    raw=add(7900,'G3D_SaveMesh','reconstruct','Save RAW untextured reconstruction',mesh=reconstructed,job_id=job,artifact_key='reconstruction')
    add(7901,'Preview3DAdvanced','reconstruct',model_3d=['7900',1],viewport_state='',width=1024,height=1024)

    # Independent single-image weights and conditioning for the proxy branch.
    proxy=remap(shape,4000)
    for node in proxy.values():
        node['_meta']['fvb_stage']='proxy'
    # Remove matrix/multiview leaves; original is its only appearance/geometry evidence.
    for ident in [str(7710+4000), *[str(7720+i+4000) for i in range(len(selected_views(s)))]]:
        proxy.pop(ident,None)
    proxy['4324']=dict(class_type='Pixal3DConditioning',inputs={'clip_vision_model':['4015',0],'image':['4702',0],'camera_angle_x':['4705',0]},_meta={'title':'Single original image → Pixal3D','fvb_stage':'proxy'})
    proxy['4319']['inputs']['unet_name']=model('pixal_single')
    proxy['4094']['inputs']['target_resolution']=s['proxy_resolution']
    for ident,seed,steps in [('4003',s['proxy_seed']+14,s['structure_steps']),('4018',s['proxy_seed'],s['shape_steps']),('4023',s['proxy_seed'],s['upscale_steps'])]:
        proxy[ident]['inputs'].update(seed=seed,steps=steps,cfg=s['mesh_cfg'])
    graph.update(proxy)
    load(4700,'original','proxy')
    bg=add(4701,'LoadBackgroundRemovalModel','proxy',bg_removal_name=model('birefnet'))
    processing=s.get('proxy_processing')=='upright_solid_box'
    prep=add(4702,'G3D_PrepareImage','proxy','Original cutout — single-image fit',image=['4700',0],bg_removal_model=bg,mode='pixal_fit' if processing else 'fit',padding=1.1)
    save(4709,prep,'proxy:input','proxy')
    if processing:
        rgb=add(4712,'G3D_ResizeReference','proxy','One black RGB frame for both FoV and Pixal',image=prep,size=1024)
        save(4713,rgb,'proxy:conditioning_input','proxy')
        proxy['4324']['inputs']['image']=rgb
        graph['4324']['inputs']['image']=rgb
    else:rgb=prep
    moge=add(4703,'LoadMoGeModel','proxy',model_name=model('moge2'))
    geometry=add(4704,'MoGeInference','proxy',moge_model=moge,image=rgb,resolution_level=9,fov_x_degrees=0,batch_size=1,force_projection=True,apply_mask=True,refine_steps=0)
    fov=add(4705,'MoGeGeometryToFOV','proxy',moge_geometry=geometry,axis='horizontal',unit='degrees')
    add(4706,'G3D_RecordValue','proxy','Save original FOV estimate',value=fov,job_id=job,artifact_key='proxy:fov')
    for ident,source in [(4710,'4108'),(4711,'4126')]:
        add(ident,'AW_ModelBudget','proxy',model=[source,0],extra_gb=s['extra_vram_headroom_gb'])
    graph['4003']['inputs']['model']=['4710',0]
    for ident in ('4018','4023'):
        graph[ident]['inputs']['model']=['4711',0]
    painted=['4092',0]
    if s.get('guide_material','source_color')=='source_color':
        texture_vae=add(4720,'VAELoader','proxy',vae_name=model('texture_vae'))
        tex=add(4721,'Trellis2TextureStage','proxy',positive=['4094',0],negative=['4094',1],shape_latent=['4023',0])
        matmodel=add(4722,'AW_ModelBudget','proxy',model=['4319',0],extra_gb=s['extra_vram_headroom_gb'])
        matsample=add(4723,'KSampler','proxy',model=matmodel,positive=tex,negative=['4721',1],latent_image=['4721',2],seed=s['proxy_seed']+1,
            steps=s['proxy_color_steps'],cfg=s['proxy_color_cfg'],sampler_name='euler',scheduler='normal',denoise=1.0)
        colors=add(4724,'VaeDecodeTextureTrellis','proxy',samples=matsample,vae=texture_vae,shape_subdivides=['4092',1])
        painted=add(4725,'PaintMesh','proxy',mesh=['4092',0],voxel_colors=colors)
    if processing:
        raw_proxy=add(4776,'G3D_SaveMesh','proxy','Preserve raw decoder output — not the working proxy',mesh=painted,job_id=job,artifact_key='proxy:raw')
        oriented=add(4777,'G3D_OrientProxy','proxy','AUTOMATIC working proxy — estimated box pose',mesh=raw_proxy,job_id=job,policy=s['proxy_processing'])
        remeshed=add(4778,'RemeshMesh','proxy','Native topology repair — solid closed prop',mesh=oriented,resolution=s['proxy_remesh_resolution'],
            **{'sign_mode':'solid','sign_mode.fill':20.,'sign_mode.qef':False},band=1.,project_back=0.,fix_poles=False,
            smooth_iters=s['proxy_smooth_iterations'],drop_small_components=.001,precluster_max_verts=20000000)
        painted=add(4779,'G3D_FinalizeProxy','proxy','Ground and record the actual working mesh',mesh=remeshed,job_id=job,
            orientation_report=['4777',1],resolution=s['proxy_remesh_resolution'],smooth_iterations=s['proxy_smooth_iterations'])
    add(4780,'G3D_SaveMesh','proxy','Save WORKING proxy used by preview and Blender',mesh=painted,job_id=job,artifact_key='proxy')
    add(4781,'Preview3DAdvanced','proxy',model_3d=['4780',1],viewport_state='',width=1024,height=1024)

    add(4900,'G3D_RenderProxy','render','Blender known-camera guides',job_id=job)
    if s['enhancement_mode']=='sheet':
        cameras=add(5100,'G3D_ReadCameras','sheet',job_id=job,selected_only=False,source='render')
        guides={ident:load(5101+i,'render:'+ident,'sheet') for i,ident in enumerate(('front','right','back','left'))}
        packed=add(5110,'G3D_PackSheet','sheet','Fixed panels + black gutters; save exact layout',
            job_id=job,camera_manifest=cameras,gutter=s['sheet_gutter'],**guides)
        add(5111,'PreviewImage','sheet',images=packed)
        controlled=s['structure_control']!='off'
        if controlled:
            edge_inputs={}
            if s['structure_control']=='canny':
                for i,ident in enumerate(('front','right','back','left')):
                    edge_inputs[ident]=add(5121+i,'Canny','sheet',image=guides[ident],
                        low_threshold=s['canny_low_threshold'],high_threshold=s['canny_high_threshold'])
            control=add(5130,'G3D_ControlSheet','sheet','Registered structural sheet + foreground mask',
                job_id=job,layout_json=['5110',1],control_mode=s['structure_control'],
                mask_threshold=s['mask_threshold'],mask_dilation_px=s['mask_dilation_px'],
                canny_low_threshold=s['canny_low_threshold'],canny_high_threshold=s['canny_high_threshold'],**edge_inputs)
            add(5131,'PreviewImage','sheet',images=control)
            mask_preview=add(5132,'MaskToImage','sheet',mask=['5130',1])
            add(5133,'PreviewImage','sheet',images=mask_preview)
        prompt,refs=sheet_enhancement(s);inputs={}
        for i,ref in enumerate(refs):
            image=load(6500+i*2,ref['key'],'enhance_sheet')
            if i:
                image=add(6501+i*2,'G3D_ResizeReference','enhance_sheet',ref['description'],image=image,
                    size=1024 if i<=2 else s['supplementary_resolution'])
            inputs['image_'+str(i+1)]=image
        qm=add(6530,'UNETLoader','enhance_sheet',unet_name=model('qwen21'),weight_dtype='default')
        qm=add(6532,'QwenImage21Cache','enhance_sheet',model=qm,
            device=s['controlled_cache_device'] if controlled else s['cache_device'],dtype=s['cache_dtype'])
        qm=add(6533,'AW_ModelBudget','enhance_sheet',model=qm,extra_gb=s['extra_vram_headroom_gb'])
        qc=add(6534,'CLIPLoader','enhance_sheet',clip_name=model('qwen21_clip'),type='qwen_image',device='default')
        qv=add(6535,'VAELoader','enhance_sheet',vae_name=model('qwen21_vae'))
        if controlled:
            qv=add(6540,'G3D_ControlVAE','enhance_sheet',vae=qv,tiled_encode=s['tiled_vae'])
            patch=add(6541,'ModelPatchLoader','enhance_sheet',name=model('qwen21_union'))
            control=add(6542,'G3D_LoadControl','enhance_sheet',job_id=job,canvas=inputs['image_1'])
            inpaint={'inpaint_image':inputs['image_1'],'mask':['6542',1]} if s['mask_mode']=='foreground' else {}
            qm=add(6543,'ZImageFunControlnet','enhance_sheet','Native Qwen 2.1 Union — registered structure',
                model=qm,model_patch=patch,vae=qv,image=control,strength=s['control_strength'],
                start_percent=s['control_start_percent'],end_percent=s['control_end_percent'],**inpaint)
        cond=add(6536,'G3D_QwenSheetEncode','enhance_sheet','Sheet edit: geometry first, appearance second, concept third',
            clip=qc,vae=qv,prompt=prompt,negative_prompt='',tiled_encode=s['tiled_vae'],**inputs)
        sampled=add(6537,'KSampler','enhance_sheet',model=qm,positive=cond,negative=['6536',1],latent_image=['6536',2],
            seed=s['enhancement_seed'],steps=s['enhancement_steps'],cfg=s['enhancement_cfg'],sampler_name='euler',scheduler='simple',denoise=1.0)
        image=decode(6538,sampled,qv,'enhance_sheet')
        if controlled:
            add(6539,'G3D_FinalizeSheet','enhance_sheet','Keep raw sheet; restore fixed black gutters only',
                image=image,job_id=job,restore_black_gutters=s['restore_black_gutters'])
        else:save(6539,image,'enhanced:sheet','enhance_sheet')
        sheet=load(6600,'enhanced:sheet','split')
        split=add(6601,'G3D_SplitSheet','split','Exact crops; preserve all four; review selection before reconstruction',image=sheet,job_id=job)
        for i in range(4):add(6610+i,'PreviewImage','split',images=['6601',i])

    for i,v in enumerate(view_records(s)):
        base=5000+i*10
        image=load(base,'render:'+v['id'],'render_preview')
        add(base+1,'PreviewImage','render_preview',images=image)
    for i,v in enumerate(view_records(s) if s['enhancement_mode']=='individual' else []):
        b=6000+i*100; stage='enhance:'+v['id']
        override=s.get('view_overrides',{}).get(v['id'],{})
        prompt,refs=enhancement(s,v['id'])
        inputs={}
        for j,ref in enumerate(refs):
            image=load(b+j*2,ref['key'],stage)
            size=1024 if j<2 else s['supplementary_resolution']
            image=add(b+j*2+1,'G3D_ResizeReference',stage,ref['description'],image=image,size=size)
            inputs['images.image_'+str(j+1)]=image
        qm=add(b+30,'UNETLoader',stage,unet_name=model('qwen21'),weight_dtype='default')
        lora=add(b+31,'LoraLoaderModelOnly',stage,model=qm,lora_name=model('qwen21_anyangle'),strength_model=s['adapter_strength'])
        qm=add(b+32,'QwenImage21Cache',stage,model=lora,device=s['cache_device'],dtype=s['cache_dtype'])
        qm=add(b+33,'AW_ModelBudget',stage,model=qm,extra_gb=s['extra_vram_headroom_gb'])
        qc=add(b+34,'CLIPLoader',stage,clip_name=model('qwen21_clip'),type='qwen_image',device='default')
        qv=add(b+35,'VAELoader',stage,vae_name=model('qwen21_vae'))
        condition=add(b+36,'TextEncodeQwenImage21',stage,'Explicit source / guide / concept roles',clip=qc,vae=qv,prompt=prompt,negative_prompt='',resolution=0,**inputs)
        sample=add(b+37,'KSampler',stage,model=qm,positive=condition,negative=[str(b+36),1],latent_image=[str(b+36),2],seed=override.get('seed',s['enhancement_seed']),
            steps=override.get('steps',s['enhancement_steps']),cfg=override.get('cfg',s['enhancement_cfg']),sampler_name='euler',scheduler='simple',denoise=1.0)
        image=decode(b+38,sample,qv,stage)
        save(b+39,image,'enhanced:'+v['id'],stage)

    bg=add(7600,'LoadBackgroundRemovalModel','prepare',bg_removal_name=model('birefnet'))
    for i,v in enumerate(view_records(s)):
        image=load(7610+i*3,'enhanced:'+v['id'],'prepare')
        prepared=add(7611+i*3,'G3D_PrepareImage','prepare','KEEP complete camera frame',image=image,bg_removal_model=bg,mode='preserve',padding=1.0)
        save(7612+i*3,prepared,'prepared:'+v['id'],'prepare')

    # Existing refine/cleanup topology, cut at saved reconstruction and enhanced view.
    finish=copy.deepcopy(baseline)
    finish['92']=dict(class_type='G3D_LoadMesh',inputs={'job_id':job,'artifact_key':'reconstruction'})
    # Corrections are independent saved stages; prepare remains an immutable original matte.
    for view,request in s.get('repair_requests',{}).items():
        b=9000+['front','right','back','left'].index(view)*40;stage='repair:'+view
        src=add(b,'G3D_RepairInput',stage,job_id=job,view_id=view)
        appearance=load(b+1,'appearance',stage)
        concept_image=load(b+2,'concept:'+view,stage)
        concept_image=add(b+3,'G3D_ResizeReference',stage,image=concept_image,size=1024)
        qm=add(b+4,'UNETLoader',stage,unet_name=model('qwen21'),weight_dtype='default')
        qm=add(b+5,'QwenImage21Cache',stage,model=qm,device='off',dtype='default')
        qm=add(b+6,'AW_ModelBudget',stage,model=qm,extra_gb=s['extra_vram_headroom_gb'])
        qc=add(b+7,'CLIPLoader',stage,clip_name=model('qwen21_clip'),type='qwen_image',device='default')
        qv=add(b+8,'VAELoader',stage,vae_name=model('qwen21_vae'))
        qv=add(b+9,'G3D_ControlVAE',stage,vae=qv,tiled_encode=s['tiled_vae'])
        patch=add(b+10,'ModelPatchLoader',stage,name=model('qwen21_union'))
        # No image/depth port: native Union encodes zero structural channels.
        qm=add(b+11,'ZImageFunControlnet',stage,'Repair surface without reinforcing defective depth',
            model=qm,model_patch=patch,vae=qv,inpaint_image=[str(b),1],mask=[str(b),2],strength=1.0,start_percent=0.0,end_percent=1.0)
        cond=add(b+12,'G3D_QwenSheetEncode',stage,'Exact single frame + original and side appearance',
            clip=qc,vae=qv,image_1=src,image_2=appearance,image_3=concept_image,
            prompt=repair_prompt(s,view),negative_prompt='',tiled_encode=s['tiled_vae'])
        sampled=add(b+13,'KSampler',stage,model=qm,positive=cond,negative=[str(b+12),1],latent_image=[str(b+12),2],
            seed=request['seed'],steps=request['steps'],cfg=request['cfg'],sampler_name='euler',scheduler='simple',denoise=1.0)
        candidate=decode(b+14,sampled,qv,stage)
        corrected=add(b+15,'G3D_CommitRepair',stage,'Save candidate + protected correction; review before mesh',job_id=job,view_id=view,image=candidate)
        add(b+16,'PreviewImage',stage,images=corrected)

    finish['7800']=dict(class_type='G3D_LoadImage',inputs={'job_id':job,'artifact_key':effective_image_key(s,effective_reference(s))})
    finish['2001']['inputs']['url']=s['hi3d_backend_url']
    finish['2020']['inputs']['image']=['7800',0]
    finish['2022']['inputs']['image']=['7800',0]
    finish['2003']['inputs'].update(resolution=s['refine_resolution'],steps=s['refine_steps'],seed=s['refine_seed'],cpu_offload=s['cpu_offload'],attention=s['attention'])
    refined=ancestor(finish,['2015'])
    # Separate save/load cuts preserve native processing links for display, without recursing into sampling.
    refined.pop('92')
    refined['7990']=finish['92']
    for node in refined.values():
        for key,value in list(node['inputs'].items()):
            if value==['92',0]: node['inputs'][key]=['7990',0]
        node['_meta']={'title':node['class_type'],'fvb_stage':'refine'}
        if 'run_name' in node['inputs']: node['inputs']['run_name']='FoundryViewBridge/'+job+'/refine'
    graph.update(refined)
    add(7991,'G3D_SaveMesh','refine','Save REFINED untextured checkpoint',mesh=['2015',0],job_id=job,artifact_key='refined')
    add(7992,'Preview3DAdvanced','refine',model_3d=['7991',1],viewport_state='',width=1024,height=1024)
    add(7993,'G3D_SaveMesh','refine','Preserve refinement BEFORE cleanup',mesh=['2003',0],job_id=job,artifact_key='refine:raw')

    texture=copy.deepcopy(baseline['2023']); texture['_meta']={'title':'Final texture — ENABLED' if s['texture_enabled'] else 'Optional final texture — OFF','fvb_stage':'texture'}
    texture['inputs'].update(mesh=['8800',0],image=['8801',0],seed=s['texture_seed'],steps=s['texture_steps'],texture_size=s['texture_size'],guidance=s['texture_guidance'],filename_prefix='FoundryViewBridge/'+job+'/texture')
    graph['2023']=texture
    add(8800,'G3D_LoadMesh','texture',job_id=job,artifact_key='refined')
    load(8801,effective_image_key(s,effective_reference(s)),'texture')
    add(8802,'G3D_SaveFile','texture',model_3d=['2023',0],job_id=job,artifact_key='textured')
    add(8803,'Preview3DAdvanced','texture',model_3d=['2023',0],viewport_state='',width=1024,height=1024)
    return graph


def endpoints(stage,spec):
    if stage=='concept': return ['903','1580', *[str(1591+i*2) for i in range(4)]]
    if stage=='proxy': return ['4706','4709','4780','4781',*(['4713'] if spec.get('proxy_processing')=='upright_solid_box' else [])]
    if stage=='render': return ['4900']
    if stage=='sheet': return ['5110','5111',*(['5130','5131','5133'] if spec.get('structure_control','off')!='off' else [])]
    if stage=='enhance_sheet': return ['6539']
    if stage=='split': return ['6601','6610','6611','6612','6613']
    if stage=='render_preview': return [str(5001+i*10) for i in range(len(view_records(spec)))]
    if stage.startswith('enhance:'):
        index=next(i for i,v in enumerate(view_records(spec)) if v['id']==stage.split(':')[1])
        return [str(6039+index*100)]
    if stage=='prepare': return [str(7612+i*3) for i in range(len(view_records(spec)))]
    if stage.startswith('repair:'):
        view=stage.split(':')[1]
        if view not in spec['repair_requests']:raise ValueError('No repair requested for '+view)
        i=['front','right','back','left'].index(view);return [str(9015+i*40),str(9016+i*40)]
    if stage=='reconstruct': return ['7900','7901']
    if stage=='refine': return ['7991','7992','7993']
    if stage=='texture' and spec['texture_enabled']: return ['8802','8803']
    raise ValueError('Unknown or disabled stage: '+stage)


def compile_stage(stage,spec,artifacts):
    graph=ancestor(canonical_api(spec),endpoints(stage,spec))
    for node in graph.values():
        node.pop('_meta',None)
    return graph


def editable_api(spec=None):
    spec={**(sheet_defaults() if spec is None else defaults()),**(spec or {})}
    graph=canonical_api(spec)
    graph['9900']={'class_type':'G3D_ReviewControl','inputs':{
        'operation':'readiness','settings_json':json.dumps(spec,indent=2),'job_id':spec['job_id']},
        '_meta':{'title':'START HERE · readiness only · choose the object later','fvb_stage':'control'}}
    graph['9901']={'class_type':'PreviewAny','inputs':{'source':['9900',0]},
        '_meta':{'title':'READINESS / REVIEW STATUS — no asset generated','fvb_stage':'control'}}
    if spec['enhancement_mode']=='sheet':
        graph['9902']={'class_type':'G3D_ViewSelection','inputs':{
            'include_'+v:v in spec['selected_view_ids'] for v in ('front','right','back','left')},
            '_meta':{'title':'USE ONLY CONSISTENT VIEWS · any nonempty subset · all outputs preserved','fvb_stage':'control'}}
        graph['9900']['inputs']['view_selection']=['9902',0]
    if spec.get('repair_enabled'):
        graph['9930']={'class_type':'G3D_RepairControl','inputs':dict(operation='status',job_id=spec['job_id'],view_id='back',
            ticket_id='',mask_filename='',prompt='Keep this view of the same chest. Replace the faulty rear surface with solid red painted wood; preserve the surrounding iron hinges and bands.',
            seed=42,steps=40,cfg=1.0,margin_px=8,feather_px=4),
            '_meta':{'title':'OPTIONAL REPAIR · prepare editor → paint → apply request → explicit Resume','fvb_stage':'repair_control'}}
        graph['9931']={'class_type':'PreviewAny','inputs':{'source':['9930',0]},'_meta':{'title':'Repair status / source / applied request','fvb_stage':'repair_control'}}
        graph['9932']={'class_type':'LoadImage','inputs':{'image':''},'_meta':{'title':'PAINT HERE · source loaded by prepare_editor · Save to Node','fvb_stage':'repair_control'}}
    return graph
