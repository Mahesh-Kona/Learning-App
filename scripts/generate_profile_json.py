#!/usr/bin/env python3
"""Login as student@example.com, fetch profile, and write dynamic JSON file.

Usage: run from project root with venv Python.
"""
import requests, os, json, sys

base = 'http://127.0.0.1:5000'
creds = {'email': 'student@example.com', 'password': 'StudentPass1'}

try:
    r = requests.post(base + '/api/v1/auth/login', json=creds)
except Exception as e:
    print('Login request failed:', e)
    sys.exit(1)

print('login status', r.status_code)
if r.status_code != 200:
    print(r.text)
    sys.exit(1)

data = r.json()
access = data.get('access_token')
user = data.get('user') or {}
uid = user.get('id')
print('got token for user', user)

if not access or not uid:
    print('Missing token or uid')
    sys.exit(1)

headers = {'Authorization': f'Bearer {access}'}

try:
    p = requests.get(base + f'/api/v1/profile/{uid}', headers=headers)
except Exception as e:
    print('Profile request failed:', e)
    sys.exit(1)

print('/profile', p.status_code)
try:
    print(p.json())
except Exception:
    print(p.text)

if p.status_code != 200:
    print('Profile fetch failed')
    sys.exit(1)

payload = p.json()

# ensure dynamic_json dir exists
dyn = os.path.join('instance', 'dynamic_json')
os.makedirs(dyn, exist_ok=True)
out_path = os.path.join(dyn, f'user_{uid}_profile.json')

with open(out_path, 'w', encoding='utf8') as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)

print('Wrote', out_path)
