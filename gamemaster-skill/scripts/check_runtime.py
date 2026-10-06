#!/usr/bin/env python3
"""Read-only dependency preflight. Does not install or download anything."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def check(feature, font=None):
    result = {'python': sys.version_info >= (3, 10)}
    if feature == 'xlsx':
        result['openpyxl'] = importlib.util.find_spec('openpyxl') is not None
    if feature == 'pdf':
        result['reportlab'] = importlib.util.find_spec('reportlab') is not None
        result['font_file'] = bool(font and Path(font).is_file())
    if feature == 'docx':
        node = shutil.which('node')
        result['node_docx'] = False
        if node:
            # Resolution matches the actual renderer, including sibling node_modules/NODE_PATH.
            script_dir = str(Path(__file__).resolve().parent)
            run = subprocess.run([node, '-e', "require.resolve('docx', {paths:[process.argv[1]]})", script_dir],
                                 capture_output=True, timeout=15)
            result['node_docx'] = run.returncode == 0
    if feature == 'latex':
        result['tex_engine'] = bool(shutil.which('xelatex') or shutil.which('tectonic'))
        result['cache_note'] = 'Compiler presence only; macro/font cache is verified by an offline trial render'
    return {'feature': feature, 'ready': all(v for v in result.values() if isinstance(v, bool)), 'checks': result}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feature', choices=['core', 'xlsx', 'pdf', 'docx', 'latex'], default='core')
    p.add_argument('--font-file')
    a = p.parse_args()
    r = check(a.feature, a.font_file)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r['ready'] else 1)
