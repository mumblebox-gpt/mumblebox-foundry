"""Reject partially accepted stage graphs before treating them as production."""
def rejection(result,status):
    if status<400 and not result.get('node_errors'):return None
    return 'Comfy rejected required stage nodes: '+str(result.get('error',{}))+'. Node errors: '+str(result.get('node_errors',{}))
