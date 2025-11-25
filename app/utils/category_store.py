import json
import os
from threading import Lock

_lock = Lock()

def _store_path(app_root=None):
    # store under instance/ if available, else app root
    base = app_root or os.getcwd()
    inst = os.path.join(base, 'instance')
    if not os.path.isdir(inst):
        try:
            os.makedirs(inst, exist_ok=True)
        except Exception:
            inst = base
    return os.path.join(inst, 'categories.json')

def read_categories(app_root=None):
    path = _store_path(app_root)
    try:
        with _lock:
            if not os.path.exists(path):
                return []
            with open(path, 'r', encoding='utf8') as fh:
                data = json.load(fh) or []
            # ensure list of dicts with name
            out = []
            for it in data:
                if isinstance(it, str):
                    out.append({'name': it})
                elif isinstance(it, dict) and 'name' in it:
                    out.append(it)
            return out
    except Exception:
        return []

def write_category(cat, app_root=None):
    path = _store_path(app_root)
    try:
        with _lock:
            data = []
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf8') as fh:
                        data = json.load(fh) or []
                except Exception:
                    data = []
            # normalize to dict
            name = cat.get('name') if isinstance(cat, dict) else str(cat)
            if not name:
                return False
            # avoid duplicates (case-insensitive)
            exists = False
            for item in data:
                item_name = item.get('name') if isinstance(item, dict) else item
                if isinstance(item_name, str) and item_name.lower() == name.lower():
                    exists = True
                    break
            if not exists:
                data.append(cat if isinstance(cat, dict) else {'name': name})
            with open(path, 'w', encoding='utf8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            return True
    except Exception:
        return False


def remove_category(name, app_root=None):
    """Remove a category by name (case-insensitive) from the store.
    Returns True if an item was removed, False otherwise.
    """
    if not name:
        return False
    path = _store_path(app_root)
    try:
        with _lock:
            if not os.path.exists(path):
                return False
            try:
                with open(path, 'r', encoding='utf8') as fh:
                    data = json.load(fh) or []
            except Exception:
                data = []

            lowered = name.lower()
            new_data = []
            removed = False
            for item in data:
                item_name = item.get('name') if isinstance(item, dict) else item
                if isinstance(item_name, str) and item_name.lower() == lowered:
                    removed = True
                    continue
                new_data.append(item)

            if not removed:
                return False

            with open(path, 'w', encoding='utf8') as fh:
                json.dump(new_data, fh, ensure_ascii=False, indent=2)
            return True
    except Exception:
        return False
