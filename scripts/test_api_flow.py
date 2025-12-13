import requests, json, os, sys
base='http://127.0.0.1:5000'
try:
    login = requests.post(base+'/api/v1/auth/login', json={'email':'student@example.com','password':'StudentPass1'})
except Exception as e:
    print('Request failed:', e)
    sys.exit(1)
print('login status', login.status_code)
if login.status_code!=200:
    print(login.text)
    sys.exit(1)
access = login.json().get('access_token')
user = login.json().get('user')
print('got token for user', user)
headers={'Authorization': f'Bearer {access}'}
resp = requests.get(base+'/api/v1/courses', headers=headers)
print('/courses', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text)
# get lessons for course id 1
resp2 = requests.get(base+'/api/v1/courses/1/lessons', headers=headers)
print('/courses/1/lessons', resp2.status_code)
try:
    print(resp2.json())
except Exception:
    print(resp2.text)
# update progress by lesson_id
resp3 = requests.post(base+'/api/v1/progress/update', headers={**headers, 'Content-Type':'application/json'}, json={'lesson_id':1, 'time_spent':5, 'score':99})
print('/progress/update', resp3.status_code)
try:
    print(resp3.json())
except Exception:
    print(resp3.text)
# check generated JSON file
uid = user.get('id')
path = os.path.join('instance','dynamic_json', f'user_{uid}_progress.json')
print('expected json path', path)
if os.path.exists(path):
    print('file exists. content:\n', open(path,'r', encoding='utf-8').read())
else:
    print('file not found')
