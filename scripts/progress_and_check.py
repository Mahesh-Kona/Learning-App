import requests, os, sys
base='http://127.0.0.1:5000'
email='student@example.com'
password='StudentPass1'
# login
r = requests.post(base+'/api/v1/auth/login', json={'email':email,'password':password})
print('login', r.status_code)
if r.status_code!=200:
    print(r.text); sys.exit(1)
access = r.json().get('access_token')
user = r.json().get('user')
print('user', user)
headers={'Authorization': f'Bearer {access}', 'Content-Type':'application/json'}
# use lesson id known from seed/demo
lesson_id = 11
user_id = user.get('id')
# This API expects user_id + lesson_id in the payload
pj = requests.post(base+'/api/v1/progress', json={'user_id': user_id, 'lesson_id':lesson_id, 'time_spent':10, 'score':95})
print('/progress/update', pj.status_code)
try:
    print(pj.json())
except Exception:
    print(pj.text)
# check generated file
uid = user.get('id')
path = os.path.join('instance','dynamic_json', f'user_{uid}_progress.json')
print('expected path', path)
if os.path.exists(path):
    print('file exists, size', os.path.getsize(path))
    print(open(path,'r',encoding='utf8').read())
else:
    print('file not found')
