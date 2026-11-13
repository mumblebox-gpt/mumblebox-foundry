import {ux} from './settings.js';

export function settingsProblem(group, values) {
    if (group === 'orbit') return orbitProblem(values);
    if (group === 'meshroom' && values.minimum_checked_fov >= values.maximum_checked_fov)
        return ux('camera_range');
    if (group === 'turnaround' && 'sigmas' in values) {
        const sigmas=values.sigmas.split(',').map(value=>value.trim()?Number(value):NaN);
        if (sigmas.length<2||sigmas.length>101||!(sigmas[0]>0&&sigmas[0]<=1)||sigmas.at(-1)!==0||
            sigmas.slice(1).some((value,index)=>!(value>=0&&value<sigmas[index]))) return ux('invalid_sigmas');
    }
    for(const key of ['advanced_overrides','advanced_texture']){
        if(!(key in values))continue;
        try {
            const json=JSON.parse(values[key]);
            if(!json||typeof json!=='object'||Array.isArray(json))return ux('invalid_json');
        }catch{return ux('invalid_json');}
    }
    return null;
}

function orbitProblem(orbit) {
    if (!Number.isInteger(orbit.length) || (orbit.length - 5) % 17 ||
        orbit.width % 32 || orbit.height % 32) return ux('invalid_video');
    if (!(orbit.three_quarter_fraction < orbit.side_fraction && orbit.side_fraction < orbit.back_fraction))
        return ux('invalid_guide_order');
    if (orbit.decode_overlap * 2 > orbit.decode_tile || orbit.temporal_overlap * 2 > orbit.decode_frames)
        return ux('invalid_overlap');
    return null;
}

const equal = (a,b) => {
    if(a===b)return true;
    if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;
    const keys=Object.keys(a);
    return keys.length===Object.keys(b).length&&keys.every(key=>Object.hasOwn(b,key)&&equal(a[key],b[key]));
};

export function firstChangedStage(draft, run) {
    if (!run) return null;
    const before = run.controls;
    const now = draft.controls;
    if (run.references?.[0]?.filename !== draft.image || !equal(before.turnaround, now.turnaround))
        return 'turnaround';
    if (!equal(before.orbit, now.orbit)) return 'orbit';
    if (!equal(before.frames, now.frames)) return now.camera ? 'cameras' : 'reconstruct';
    if (now.camera) {
        if (!equal(before.camera, now.camera)) return 'cameras';
        if (!equal(before.views, now.views)) return 'views';
        if (!equal(before.pixal, now.pixal) || !equal(run.exclude_views || [], draft.exclude_views || []))
            return 'reconstruct';
    } else if (run.engine !== draft.engine || !equal(before[draft.engine], now[draft.engine])) {
        return 'reconstruct';
    }
    if (!equal(before, now) || !equal(run.selection, draft.selection) || !equal(run.overrides, draft.overrides))
        return 'finish';
    return null;
}

export const operations = {
    turnaround:'turnaround_stage',orbit:'orbit_stage',cameras:'camera_stage',views:'views_stage',
    reconstruct:'mesh_stage',finish:'finish_stage',
};
