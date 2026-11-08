"""HairDeck output adaptation, retaining upstream export behavior and adding official per-card colors.

Save orchestration adapted from FengLairh/ComfyUI-HairDeck 1abc5c1 (Apache-2.0).
Native helpers remain the owners of GLB, VRM, motion, materials and rendering.
"""
import json
import shutil
import tempfile
from pathlib import Path
import numpy as np
from hairdeck_core import materials
from hairdeck_core.cards.mesh import cards_to_json
from comfy_api.latest import io, ui
import folder_paths
from .integration import upstream
from .appearance import create_appearance

def save(cls, result, format, filename_prefix, color, show_head, show_chains, save_debug, blender_path, head_profile='auto',
         uv_mode='共享图集', texture_size='2K', material_preset='体积发束', motion_chains=False):
    native=upstream();exporting=native.output.exporting;runtime=native.runtime;heads=native.heads
    FORMATS=native.output.FORMATS;UV_MODES=native.output.UV_MODES
    MATERIAL_PRESETS=native.output.MATERIAL_PRESETS;TEXTURE_SIZES=native.output.TEXTURE_SIZES
    new_directory=native.output.new_directory;file_entry=native.output.file_entry
    SavedOutput=native.output.SavedOutput
    if format not in FORMATS:
        raise ValueError('不支持的保存格式。')
    animated = format != 'GLB'
    if (animated or show_chains) and result.rig is None:
        raise ValueError('请在生成节点开启“生成弹簧骨骼”，然后重新生成。')
    if uv_mode not in UV_MODES or texture_size not in TEXTURE_SIZES or material_preset not in MATERIAL_PRESETS:
        raise ValueError('请选择有效的 UV 模式、贴图尺寸和材质预设。')
    rgb = exporting.validate(result.hair, result.rig, color)
    head = heads.resolve(result.hair.root, head_profile)
    if animated:
        exporting.resolve_blender(result.hair.root, blender_path)
    directory = new_directory(filename_prefix)
    relative = directory.relative_to(Path(folder_paths.get_output_directory()).resolve()).as_posix()
    temporary = Path(folder_paths.get_temp_directory()).resolve() / 'hairdeck'
    temporary.mkdir(parents=True, exist_ok=True)
    asset_work = Path(tempfile.mkdtemp(prefix='surface_', dir=temporary))
    asset = create_appearance(result.hair, rgb, color, UV_MODES[uv_mode], TEXTURE_SIZES[texture_size],
                             MATERIAL_PRESETS[material_preset], directory / 'textures', asset_work)
    appearance = str(asset.descriptor)
    files = []
    model_path = exporting.save_glb(result.hair, result.rig if show_chains else None, show_head, color, relative + '/hair', head, appearance)
    files.append(file_entry(model_path, 'GLB 模型', 'model'))
    if animated:
        avatar_path, preview = exporting.save_vrm(result.hair, result.rig, color, relative + '/avatar', blender_path, head, appearance)
        files.append(file_entry(avatar_path, 'VRM 角色', 'model'))
        files.append(file_entry(avatar_path.with_suffix('.check.json'), 'VRM 检查记录', 'data'))
    else:
        preview = native.output.glb_preview(result.hair.root, model_path, directory / 'model_views.png')
    primary = ui.ImageSaveHelper.save_images(preview, filename_prefix=relative + '/preview',
                                             folder_type=io.FolderType.output, cls=cls)[0]
    files.append(dict(primary, label='模型多视图', kind='image'))
    if format == 'GLB + VRM + 动画':
        motion_path, motion = exporting.save_motion(result.hair, result.rig, motion_chains, color, relative + '/motion', head, appearance)
        files.append(dict(motion, label='动画预览', kind='video'))
    for filename, label in [('base_color.png', '发色与透明度'), ('normal.png', '发丝法线'), ('roughness.png', '粗糙度'),
                            ('metallic_roughness.png', 'glTF 金属粗糙度'), ('unity_metallic_smoothness.png', 'Unity 金属光滑度'),
                            ('alpha.png', '透明度'), ('uv_layout.png', 'UV 布局'),
                            ('material.json', '材质与网格数据说明')]:
        files.append(file_entry(directory / 'textures' / filename, label, 'data' if filename.endswith('.json') else 'image'))
    if save_debug:
        shutil.copyfile(asset_work / 'surface.npz', directory / 'surface.npz')
        files.append(file_entry(directory / 'surface.npz', '优化表面数据', 'data'))
        debug_images = [('model_input', result.crop, '模型输入图'), ('preprocess', result.preview, '预处理图'),
                        ('hair_mask', result.hair_mask[..., None].expand(-1, -1, -1, 3), '头发蒙版'),
                        ('face_mask', result.face_mask[..., None].expand(-1, -1, -1, 3), '面部蒙版')]
        for name, image, label in debug_images:
            image_file = ui.ImageSaveHelper.save_images(image, filename_prefix=relative + '/' + name,
                                                         folder_type=io.FolderType.output, cls=cls)[0]
            files.append(dict(image_file, label=label, kind='image'))
        card_data=cards_to_json(result.hair.cards)
        if getattr(result.hair,'card_colors',None) is not None:
            for card,colors in zip(card_data,result.hair.card_colors):card['colors']=np.asarray(colors).tolist()
        (directory / 'cards.json').write_text(json.dumps(card_data), encoding='utf-8')
        np.save(directory / 'tokens.npy', result.hair.tokens, allow_pickle=False)
        files.extend([file_entry(directory / 'cards.json', '发片曲线', 'data'),
                      file_entry(directory / 'tokens.npy', '生成特征', 'data')])
        if result.rig is not None:
            (directory / 'chains.json').write_text(json.dumps(result.rig.chains), encoding='utf-8')
            files.append(file_entry(directory / 'chains.json', '骨骼链数据', 'data'))
    manifest = dict(format_version=1, hair_cards=len(result.hair.cards),
                    generated_chains=len(result.rig.chains) if result.rig else 0,
                    seed=result.seed, steps=result.steps, cfg=result.cfg,
                    generation_seconds=result.seconds, preprocess_cache_hit=result.preprocess_cache_hit,
                    saved_format=format, base_head=head.name if head else 'upstream',
                    uv_mode=asset.material['uv_mode'], material_preset=material_preset, texture_size=texture_size,
                    predicted_colors=getattr(result.hair,'card_colors',None) is not None and color=='auto',
                    geometry=asset.material['geometry'], files=files)
    manifest_path = directory / 'result.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    files.append(file_entry(manifest_path, '结果清单', 'data'))
    summary = f'{len(result.hair.cards)} 张发片 · {manifest["generated_chains"]} 条骨骼链 · {manifest["base_head"]} · 保存完成'
    return SavedOutput(directory, model_path,
                       dict(images=[primary], hairdeck_files=files, hairdeck_summary=[summary]))
