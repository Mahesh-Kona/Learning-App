#!/usr/bin/env python3
"""Print Flask app URL map as JSON, filtered to endpoints defined in `app.routes.api`.

This script ensures the repository root is on `sys.path` so it can be run
directly from the project root in PowerShell or other shells.
"""
import os
import sys
import json

# Ensure repo root is on sys.path (so `import app` works when running from scripts/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app

app = create_app()
with app.app_context():
    routes = []
    for r in app.url_map.iter_rules():
        # Skip non-API routes quickly
        if not r.rule.startswith('/api'):
            continue

        # Resolve the view function and check its module
        view_fn = app.view_functions.get(r.endpoint)
        mod = view_fn.__module__ if view_fn is not None else None

        # Only include endpoints whose function lives in `app.routes.api`
        if mod and mod.startswith('app.routes.api'):
            routes.append({
                'rule': r.rule,
                'methods': sorted([m for m in r.methods if m not in ('HEAD', 'OPTIONS')]),
                'endpoint': r.endpoint,
                'module': mod,
            })

    print(json.dumps(routes, indent=2))
