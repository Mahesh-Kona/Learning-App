from flask import Blueprint, Response

bp = Blueprint('demo', __name__)


@bp.route('/demo')
def demo():
    html = '''<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Flask Backend Demo</title>
  <style>
    body{font-family:Segoe UI, Roboto, Arial; padding:16px}
    .password-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:9999}
    .password-box{background:white;padding:30px;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.3);text-align:center}
    .password-box input{padding:10px;font-size:16px;width:250px;margin:10px 0;border:1px solid #ccc;border-radius:4px}
    .password-box button{padding:10px 20px;font-size:16px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer}
    .password-box button:hover{background:#0056b3}
    .hidden{display:none !important}
  </style>
</head>
<body>
  <div id="passwordOverlay" class="password-overlay">
    <div class="password-box">
      <h2>Access Protected Demo</h2>
      <p>Enter password to access this page:</p>
      <input id="demoPass" type="password" placeholder="Password" />
      <br />
      <button onclick="checkPassword()">Access</button>
    </div>
  </div>

  <div id="mainContent" class="hidden">
    <h2>Flask Learning Backend — Demo</h2>
    <p>Use the controls below to call the API and verify JSON responses in your browser.</p>

    <h3>Register</h3>
    <input id="regEmail" placeholder="email"  />
    <input id="regPass" placeholder="password"  />
    <select id="regRole">
      <option value="admin" selected>Admin</option>
    </select>
    <button onclick="register()">Register</button>

    <h3>Response</h3>
    <pre id="output" style="background:#f6f8fa;padding:8px;border:1px solid #ddd;max-height:200px;overflow:auto"></pre>
  </div>

  <script>
    const DEMO_PASSWORD = 'edusaint_admin_321';
    
    function checkPassword(){
      const pass = document.getElementById('demoPass').value;
      if(pass === DEMO_PASSWORD){
        document.getElementById('passwordOverlay').classList.add('hidden');
        document.getElementById('mainContent').classList.remove('hidden');
      } else {
        alert('Incorrect password');
        document.getElementById('demoPass').value = '';
      }
    }

    document.getElementById('demoPass').addEventListener('keypress', function(e){
      if(e.key === 'Enter'){
        checkPassword();
      }
    });

    function out(v){ document.getElementById('output').innerText = JSON.stringify(v, null, 2); }
    function setToken(t){ localStorage.setItem('api_token', t); }
    function getToken(){ return localStorage.getItem('api_token') }

    async function register(){
      const email = document.getElementById('regEmail').value;
      const password = document.getElementById('regPass').value;
      const role = (document.getElementById('regRole') && document.getElementById('regRole').value) || 'student';
      const r = await fetch('/api/v1/auth/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email,password,role})});
      const res = await r.json();
      out(res);
      try{
        if(res && res.success){
          alert('Registration successful');
        } else {
          alert('Registration failed: ' + (res.error || JSON.stringify(res)));
        }
      }catch(e){
        // ignore alert errors
      }
    }
  </script>
</body>
</html>
'''
    return Response(html, mimetype='text/html')
