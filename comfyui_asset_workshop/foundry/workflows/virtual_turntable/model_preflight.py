"""Check the exact model names declared by the compiled native recipe."""
MODEL_FIELDS = {
    "UNETLoader": "unet_name", "CLIPLoader": "clip_name", "VAELoader": "vae_name",
    "CLIPVisionLoader": "clip_name", "LoraLoaderModelOnly": "lora_name", "LoadBackgroundRemovalModel": "bg_removal_name",
}


def check_models(graph):
    from nodes import NODE_CLASS_MAPPINGS

    missing_nodes = {item["class_type"] for item in graph.values()} - NODE_CLASS_MAPPINGS.keys()
    if missing_nodes:
        raise ValueError("Install the required ComfyUI nodes: " + ", ".join(sorted(missing_nodes)))
    missing_models = set()
    for item in graph.values():
        kind = item["class_type"]
        field = MODEL_FIELDS.get(kind)
        if not field:
            continue
        value = item["inputs"][field]
        schema = NODE_CLASS_MAPPINGS[kind].INPUT_TYPES()
        choices = schema.get("required", {}).get(field, (None,))[0]
        if isinstance(choices, (list, tuple)) and value not in choices:
            missing_models.add(value)
    if missing_models:
        raise ValueError("Install these Virtual Turntable model files in ComfyUI: " + ", ".join(sorted(missing_models)))
