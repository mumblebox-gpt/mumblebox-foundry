"""Selected-work accounting; percentages measure stages, never predicted time."""

def stage_plan(operation, selection):
    stages = []
    if operation in ('turnaround', 'rocket'): stages.append('turnaround')
    if operation in ('mesh', 'rocket'): stages.extend(('geometry', 'refinement'))
    if operation in ('finish', 'rocket'):
        selected = selection['variants']
        if any(key != 'print' for key in selected): stages.append('texture')
        stages.extend(stage for key, stage in (
            ('game_balanced', 'balanced'), ('game_compact', 'compact'),
            ('quad_light', 'quads'), ('print', 'print')) if key in selected)
        stages.append('package')
    return stages + ['cleanup']

def snapshot(run):
    if not isinstance(run.get('selection'), dict): return None
    plan = stage_plan(run.get('operation', 'rocket'), run['selection'])
    if run.get('method')=='single-image':plan=[s for s in plan if s!='turnaround']
    done = [stage for stage in plan if stage in run.get('stages', {})]
    if run.get('status') == 'complete' and run.get('cleanup',{}).get('status') != 'failed': done = list(plan)
    return {'stages': plan, 'completed': done, 'total': len(plan),
            'current': 'cleanup' if run.get('status') == 'cleaning' else run.get('stage', ''),
            'fraction': len(done) / len(plan), 'basis': 'completed stages, not elapsed time'}
