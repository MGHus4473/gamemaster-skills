"""Load optional offline validators without packaging a second copy of their algorithms."""
import importlib.util
import hashlib
import sys
from pathlib import Path


def load_core(name, core_skill=None):
    if name not in ('draw_engine', 'schedule_engine'):
        raise ValueError('Unsupported core validator')
    root = Path(core_skill).resolve() if core_skill else Path(__file__).resolve().parents[2] / 'gamemaster-skill'
    path = root / 'scripts' / (name + '.py')
    if not path.is_file():
        raise ValueError('This import adapter needs gamemaster-skill; provide --core-skill PATH')
    module_name = 'gamemaster_' + name + '_' + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load core validator')
    module = importlib.util.module_from_spec(spec)
    # dataclasses and postponed annotations resolve the defining module here.
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module
