const SOURCE_AXES = [[1,0,0],[0,1,0],[0,0,1]];

export function editAxes(state, local, joint=state.selected_joint) {
    return local && joint===state.selected_joint ? state.local_frame?.axes || SOURCE_AXES : SOURCE_AXES;
}

export function constrainedMove(origin, destination, axes, axesToKeep) {
    if (!axesToKeep || axesToKeep==="free") return destination;
    const delta = destination.map((value,index)=>value-origin[index]);
    const result = origin.slice();
    for (const axis of axesToKeep) {
        const basis = axes["XYZ".indexOf(axis)];
        if (!basis) continue;
        const distance = basis.reduce((sum,value,index)=>sum+value*delta[index],0);
        for (let i=0;i<3;i++) result[i]+=distance*basis[i];
    }
    return result;
}
