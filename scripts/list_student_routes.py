#!/usr/bin/env python3
import re, json, os
p = os.path.join('app', 'routes', 'api.py')
text = open(p, encoding='utf8').read()
pat = re.compile(r"@api_bp.route\(([^)]+)\)")
matches = pat.findall(text)
res = []
for m in matches:
    route_m = re.search(r"'([^']+)'", m)
    methods_m = re.search(r"methods\s*=\s*\[([^]]+)\]", m)
    route = route_m.group(1) if route_m else m.strip()
    methods = [x.strip().strip("'\"") for x in methods_m.group(1).split(',')] if methods_m else []
    # Only include student-friendly prefixes (blueprint prefix is applied at runtime)
    if any(route.startswith(pfx) for pfx in ['/auth', '/courses', '/lessons', '/topics', '/profile', '/progress', '/enroll', '/categories', '/search', '/cloud', '/settings', '/leaderboard']):
        res.append({'rule': route, 'methods': methods, 'url': 'http://127.0.0.1:5000' + route})
print(json.dumps(res, indent=2))
