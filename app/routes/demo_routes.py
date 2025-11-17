from flask import Blueprint, Response

bp = Blueprint('demo', __name__)


@bp.route('/demo')
def demo():
    html = '''<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Flask Backend Demo</title>
  <style>body{font-family:Segoe UI, Roboto, Arial; padding:16px} textarea{width:100%;height:120px}</style>
</head>
<body>
  <h2>Flask Learning Backend — Demo</h2>
  <p>Use the controls below to call the API and verify JSON responses in your browser.</p>

  <h3>Register</h3>
  <input id="regEmail" placeholder="email"  />
  <input id="regPass" placeholder="password"  />
  <select id="regRole">
    <option value="student" selected>Student</option>
    <option value="teacher">Teacher</option>
    <option value="admin">Admin</option>
  </select>
  <button onclick="register()">Register</button>

  <h3>Login</h3>
  <input id="logEmail" placeholder="email"  />
  <input id="logPass" placeholder="password"  />
  <button onclick="login()">Login</button>

  <h3>Actions (uses saved token)</h3>
  <button onclick="callCourses()">GET /api/v1/courses</button>
  <button onclick="callCourseDetails()">GET /api/v1/courses/{courseId}</button>
  <button onclick="callLessons()">GET /api/v1/courses/{courseId}/lessons</button>
  <button onclick="callLesson()">GET /api/v1/lessons/{lessonId}</button>
  <button onclick="callContent()">GET /api/v1/content/{lessonId}</button>
  <div style="margin-top:12px;border-top:1px solid #eee;padding-top:12px">
    <label for="fileInput">Upload file (images, pdf, mp4): </label>
    <input type="file" id="fileInput" />
    <button onclick="uploadFile()">Upload</button>
  <div id="uploadResult" style="margin-top:8px"></div>
  </div>

  <h3>Stored Token</h3>
  <pre id="tokenArea" style="background:#f6f8fa;padding:8px;border:1px solid #ddd"></pre>
  <p>Using course id: <strong id="courseIdDisplay">(loading)</strong></p>
  <p>Using lesson id: <strong id="lessonIdDisplay">(loading)</strong></p>

  <h3>Response</h3>
  <div style="display:flex;gap:12px;align-items:center">
    <div style="flex:1"><textarea id="output"></textarea></div>
    <div style="min-width:120px;text-align:center">
      <div style="font-weight:600">Cache</div>
      <div id="cacheStatus" style="padding:6px 8px;border-radius:6px;background:#eee;color:#333">(unknown)</div>
    </div>
  </div>

  <script>
    function out(v){ document.getElementById('output').value = JSON.stringify(v, null, 2); }
    function setToken(t){ localStorage.setItem('api_token', t); document.getElementById('tokenArea').innerText = t || '' }
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

    async function login(){
      const email = document.getElementById('logEmail').value;
      const password = document.getElementById('logPass').value;
      const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email,password})});
      const j = await r.json();
      out(j);
      if(j && j.access_token){ setToken(j.access_token); }
      try{
        if(j && j.access_token){
          alert('Login successful');
        } else {
          alert('Login failed: ' + (j.error || JSON.stringify(j)));
        }
      }catch(e){ }
    }

    async function callApi(path, opts){
      opts = opts || {};
      const headers = opts.headers || {};
      const token = getToken();
      if(token) headers['Authorization'] = 'Bearer ' + token;
      const r = await fetch(path, Object.assign({headers}, opts));
      let data;
      try{ data = await r.json(); } catch(e){ data = {status: r.status, text: await r.text()} }
      out({status: r.status, data});
      return data;
    }

    async function uploadFile(){
      const input = document.getElementById('fileInput');
      const file = input.files && input.files[0];
      if(!file){ alert('Please choose a file to upload'); return; }
      const fd = new FormData();
      fd.append('file', file);
      const headers = {};
      const token = getToken();
      if(token) headers['Authorization'] = 'Bearer ' + token;

      // do not display Authorization status in demo UI

      try{
        const resp = await fetch('/api/v1/uploads', { method: 'POST', headers, body: fd });
        const j = await resp.json();
        out(j);
        const resultEl = document.getElementById('uploadResult');
        resultEl.innerText = JSON.stringify(j, null, 2);
      }catch(err){
        out({success:false, error: String(err)});
      }
    }

  let firstCourseId = null;
  let firstLessonId = null;

    async function initDemo(){
      try{
        const r = await fetch('/api/v1/courses');
        const j = await r.json();
        if(j && j.data && j.data.length){
          firstCourseId = j.data[0].id;
          document.getElementById('courseIdDisplay').innerText = firstCourseId;
          // fetch lessons for the selected course and set first lesson id
          try{
            const lr = await fetch('/api/v1/courses/' + firstCourseId + '/lessons');
            const lj = await lr.json();
            if(lj && lj.data && lj.data.length){
              firstLessonId = lj.data[0].id;
              document.getElementById('lessonIdDisplay').innerText = firstLessonId;
            } else {
              document.getElementById('lessonIdDisplay').innerText = '(none)';
            }
          }catch(e){
            document.getElementById('lessonIdDisplay').innerText = '(error)';
          }
        } else {
          document.getElementById('courseIdDisplay').innerText = '(none)';
        }
      }catch(e){
        document.getElementById('courseIdDisplay').innerText = '(error)';
      }
    }

    function callCourses(){ callApi('/api/v1/courses'); }
  function callCourseDetails(){ callApi('/api/v1/courses/' + (firstCourseId || 2)); }
  function callLessons(){ callApi('/api/v1/courses/' + (firstCourseId || 2) + '/lessons'); }
    function callLesson(){ callApi('/api/v1/lessons/' + (firstLessonId || 1)); }
    async function callContent(){
      const res = await callApi('/api/v1/content/' + (firstLessonId || 1));
      try{
        const cached = res && (res.cached === true || (res.data && res.data.cached === true));
        const el = document.getElementById('cacheStatus');
        if(cached){
          el.innerText = 'Cached';
          el.style.background = '#d4f4dd';
          el.style.color = '#0b6623';
        } else {
          el.innerText = 'Fresh';
          el.style.background = '#fff4d6';
          el.style.color = '#7a4e00';
        }
      }catch(e){ /* ignore */ }
    }

    // show token if present
    document.getElementById('tokenArea').innerText = getToken() || '';
    // initialize demo (fetch first course id)
    initDemo();
  </script>
</body>
</html>
'''
    return Response(html, mimetype='text/html')
