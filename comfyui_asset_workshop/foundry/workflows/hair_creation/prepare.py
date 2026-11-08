"""First-use resource preparation. Installation and opening the UI never execute this."""
import argparse
import importlib.util
import json
from pathlib import Path


def color_resource():
    return json.loads((Path(__file__).resolve().parents[3]/'models.lock.json').read_text(encoding='utf-8'))['models']['hairdeck_color']


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pack',required=True,type=Path)
    parser.add_argument('--models-dir',required=True,type=Path)
    parser.add_argument('--with-blender',action='store_true')
    parser.add_argument('--colors',action='store_true')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('_native_hair_prepare',args.pack/'install_models.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    native.install_models(args.models_dir)
    if args.colors:
        model=color_resource()
        native.fetch(f'https://huggingface.co/{model["repo"]}/resolve/{model["revision"]}/{model["file"]}',
                     args.models_dir/model['name'],model['sha256'])
    if args.with_blender:native.install_blender(args.models_dir)
