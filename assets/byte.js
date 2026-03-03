/* BYTE by EduSaint – byte.js */
const BYTE = (() => {
  const IS_LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  const API = IS_LOCAL ? '/api/v1' : 'https://byte.edusaint.in/api/v1';
  let _student = {};

  // ── AUTH ──
  const auth = {
    get: ()      => localStorage.getItem('byte_token'),
    getR: ()     => localStorage.getItem('byte_refresh'),
    set: (a,r)   => { localStorage.setItem('byte_token',a); if(r) localStorage.setItem('byte_refresh',r); },
    clear: ()    => { localStorage.removeItem('byte_token'); localStorage.removeItem('byte_refresh'); },
    isIn: ()     => !!localStorage.getItem('byte_token'),
  };

  // ── API FETCH ──
  async function api(path, opts={}) {
    const hdrs = {'Content-Type':'application/json', ...(opts.headers||{})};
    if(auth.isIn()) hdrs['Authorization'] = `Bearer ${auth.get()}`;
    try {
      const r = await fetch(API+path, {...opts, headers:hdrs});
      if(r.status===401) {
        const ok = await _refresh();
        if(ok) return api(path,opts);
        auth.clear(); window.location='/login/'; return null;
      }
      return await r.json();
    } catch(e) { console.error('API',path,e); return null; }
  }

  async function _refresh() {
    const rt = auth.getR(); if(!rt) return false;
    try {
      const r = await fetch(API+'/auth/refresh-token',{method:'POST',headers:{'Authorization':`Bearer ${rt}`,'Content-Type':'application/json'}});
      if(!r.ok) return false;
      const d = await r.json();
      if(d.access_token){auth.set(d.access_token,null);return true;}
    } catch{}; return false;
  }

  // ── SLUG / UNSLUG ──
  function slug(s=''){
    return s.toLowerCase().replace(/[^a-z0-9\s-]/g,'').trim().replace(/\s+/g,'-').replace(/-+/g,'-');
  }
  function unslug(s=''){
    return s.replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  }

  function pathParts(){
    return window.location.pathname.split('/').filter(Boolean);
  }

  // ── COLOR ──
  function col(i){ return ((Math.abs(i)%7)+1); }

  // ── SUBJECT ICONS ──
  const ICONS={science:'🔬',math:'📐',mathematics:'📐',english:'📚',hindi:'📖',social:'🌍',history:'🏛️',geography:'🗺️',computer:'💻',biology:'🧬',physics:'⚡',chemistry:'🧪',sanskrit:'🪔',economics:'📊',politics:'⚖️',democratic:'⚖️',curiosity:'🔭',constitution:'📜'};
  function icon(name=''){
    const k=Object.keys(ICONS).find(k=>name.toLowerCase().includes(k));
    return ICONS[k]||'📘';
  }

  // ── CLASS EMOJI ──
  const CEMOJI={'1':'🌟','2':'🌈','3':'🎨','4':'🦋','5':'🌻','6':'🌱','7':'🌿','8':'🌲','9':'🚀','10':'🏆','11':'⭐','12':'🎓'};
  function cemoji(c){ return CEMOJI[String(c).trim()]||'📚'; }

  // ── ESCAPE HTML ──
  function esc(s=''){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ── TOAST ──
  let _tt;
  function toast(msg,dur=2600){
    let el=document.getElementById('b-toast');
    if(!el){el=document.createElement('div');el.id='b-toast';el.className='b-toast';document.body.appendChild(el);}
    el.textContent=msg;el.classList.add('on');
    clearTimeout(_tt);_tt=setTimeout(()=>el.classList.remove('on'),dur);
  }

  // ── SPINNER / EMPTY ──
  const spinner = ()=>`<div class="b-spin"><div class="spin"></div><p>Loading…</p></div>`;
  const empty   = (m='Nothing here yet!')=>`<div class="b-empty"><div class="ico">🔭</div><p>${esc(m)}</p></div>`;

  // ── SEO HELPERS ──
  function setMeta(title, desc, canonical){
    document.title = title;
    let md=document.querySelector('meta[name="description"]');
    if(md) md.content=desc;
    let lc=document.querySelector('link[rel="canonical"]');
    if(lc) lc.href=canonical;
  }

  // ── NAV HTML ──
  function nav(active=''){
    return `<nav class="b-nav">
      <a href="/home/" class="b-logo">
        <img src="/assets/edusaint_logo.png" alt="EduSaint" class="b-logo-icon"/>
        <span class="b-logo-text">B<em>Y</em>TE</span>
      </a>
      <div class="b-nav-mid">
        <a href="/home/" ${active==='home'?'class="active"':''}>Home</a>
        <a href="/learn/" ${active==='learn'?'class="active"':''}>Courses</a>
      </div>
      <div class="b-nav-right" id="nav-auth"></div>
    </nav>`;
  }

  function updateNav(){
    const el=document.getElementById('nav-auth'); if(!el) return;
    if(auth.isIn()){
      const name  = _student?.display_name || _student?.name || '';
      const email = _student?.email || '';
      const ini   = name.trim()
        ? (name.trim().split(' ').length>1
            ? (name.trim().split(' ')[0][0]+name.trim().split(' ')[1][0]).toUpperCase()
            : name.trim().slice(0,2).toUpperCase())
        : (email||'?').slice(0,2).toUpperCase();
      const AVCOLORS=['linear-gradient(135deg,#f59e0b,#ef4444)','linear-gradient(135deg,#8b5cf6,#ec4899)','linear-gradient(135deg,#10b981,#3b82f6)','linear-gradient(135deg,#4f46e5,#7c3aed)'];
      let h=0; for(let c of (name||email)) h=c.charCodeAt(0)+((h<<5)-h);
      const bg=AVCOLORS[Math.abs(h)%AVCOLORS.length];
      el.innerHTML=`
        <a href="/profile/" style="display:flex;align-items:center;gap:8px;text-decoration:none;color:var(--text);background:#f3f4ff;border-radius:50px;padding:5px 14px 5px 5px;transition:background .18s;" title="My Profile">
          <div style="width:30px;height:30px;border-radius:50%;background:${bg};display:flex;align-items:center;justify-content:center;font-family:'Baloo 2',sans-serif;font-size:.8rem;font-weight:900;color:#fff;">${esc(ini)}</div>
          <span style="font-weight:800;font-size:.82rem;">Profile</span>
        </a>
        <button class="b-btn b-btn-ghost" onclick="BYTE.logout()">Logout</button>`;
    } else {
      el.innerHTML=`
        <button class="b-btn b-btn-ghost" onclick="BYTE.showLoginPopup()">Login</button>
        <button class="b-btn b-btn-primary" onclick="BYTE.showLoginPopup();setTimeout(()=>BYTE._lpSwitch('r'),50)">Sign Up</button>`;
    }
  }

  function logout(){ auth.clear(); toast('Logged out 👋'); setTimeout(()=>location.href='/home/',700); }

  // ── APP DEEP LINK ──
  const APP_SCHEME = 'byteapp://';
  const APP_PLAY   = 'https://play.google.com/store/apps/details?id=in.edusaint.byte';
  const APP_IOS    = 'https://apps.apple.com/app/byte-edusaint/id0000000000';

  function openInApp(topicId, topicTitle=''){
    if(!auth.isIn()){ showLoginPopup(()=>openInApp(topicId, topicTitle)); return; }
    const deepLink = `${APP_SCHEME}topic/${topicId}`;
    window.location.href = deepLink;
    setTimeout(()=>{ showAppPrompt(topicTitle); }, 1500);
  }

  function showAppPrompt(title=''){
    const ua = navigator.userAgent.toLowerCase();
    const isIOS = /iphone|ipad|ipod/.test(ua);
    const storeUrl = isIOS ? APP_IOS : APP_PLAY;
    const storeName = isIOS ? 'App Store' : 'Play Store';
    _showModal(`
      <div style="text-align:center;padding:8px 0 4px;">
        <div style="font-size:3rem;margin-bottom:14px;">📱</div>
        <div style="font-family:'Baloo 2',sans-serif;font-size:1.3rem;font-weight:900;margin-bottom:8px;">Open in BYTE App</div>
        <div style="font-size:.86rem;color:var(--muted);font-weight:600;line-height:1.6;margin-bottom:22px;">
          ${title ? `<strong>${esc(title)}</strong><br/>` : ''}
          Interactive cards & quizzes are available in the BYTE mobile app.
        </div>
        <a href="${storeUrl}" target="_blank" style="display:block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:13px 24px;border-radius:12px;font-weight:800;font-size:.96rem;margin-bottom:10px;text-align:center;">
          Download from ${storeName} 🚀
        </a>
        <button onclick="BYTE.closeModal()" style="width:100%;padding:11px;border-radius:12px;border:2px solid var(--border);background:transparent;font-weight:700;font-size:.9rem;cursor:pointer;font-family:'Nunito',sans-serif;color:var(--muted);">
          Maybe Later
        </button>
      </div>`);
  }

  // ── GENERIC MODAL ──
  let _modalEl = null;
  function _showModal(html){
    if(!_modalEl){
      _modalEl = document.createElement('div');
      _modalEl.id = 'b-modal';
      _modalEl.innerHTML = `
        <div style="position:fixed;inset:0;z-index:600;background:rgba(15,10,50,.55);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;padding:20px;" id="b-modal-overlay" onclick="if(event.target===this)BYTE.closeModal()">
          <div style="background:#fff;border-radius:24px;max-width:380px;width:100%;padding:28px 24px;box-shadow:0 32px 80px rgba(0,0,0,.25);animation:fadeUp .25s ease-out;" id="b-modal-inner"></div>
        </div>`;
      document.body.appendChild(_modalEl);
    }
    document.getElementById('b-modal-inner').innerHTML = html;
    _modalEl.style.display = '';
  }
  function closeModal(){ if(_modalEl) _modalEl.style.display='none'; }

  // ── LOGIN POPUP ──
  let _afterLogin = null;

  function showLoginPopup(afterCb){
    _afterLogin = afterCb || null;
    let el = document.getElementById('lp-overlay');
    if(!el){
      el = document.createElement('div');
      el.id = 'lp-overlay';
      el.className = 'lp-overlay';
      el.innerHTML = _loginPopupHTML();
      document.body.appendChild(el);
      _bindLoginPopup();
    }
    _lpSwitch('l');
    document.getElementById('lp-gerr').classList.remove('on');
    requestAnimationFrame(()=>{ el.classList.add('on'); });
  }

  function closeLoginPopup(){
    const el = document.getElementById('lp-overlay');
    if(el) el.classList.remove('on');
  }

  function _loginPopupHTML(){
    return `
    <div class="lp-box" id="lp-box">
      <div class="lp-top">
        <button class="lp-close" onclick="BYTE.closeLoginPopup()">✕</button>
        <div class="lp-icon">🔐</div>
        <div class="lp-title">Login to Continue</div>
        <div class="lp-sub">Access lessons, cards & quizzes on BYTE</div>
      </div>
      <div class="lp-body">
        <div class="lp-tabs">
          <div class="lp-tab on" id="lp-tl" onclick="BYTE._lpSwitch('l')">Login</div>
          <div class="lp-tab"    id="lp-tr" onclick="BYTE._lpSwitch('r')">Sign Up</div>
        </div>
        <div class="lp-err" id="lp-gerr"></div>
        <form id="lp-fl" onsubmit="BYTE._lpLogin(event)">
          <div class="lp-field"><label>Email</label><input type="email" id="lp-le" placeholder="you@example.com" required/></div>
          <div class="lp-field"><label>Password</label><input type="password" id="lp-lp" placeholder="Your password" required/></div>
          <button type="submit" class="lp-submit" id="lp-lbtn">Login →</button>
        </form>
        <form id="lp-fr" style="display:none;" onsubmit="BYTE._lpRegister(event)">
          <div class="lp-field"><label>Name</label><input type="text" id="lp-rn" placeholder="Your name" required/></div>
          <div class="lp-field"><label>Email</label><input type="email" id="lp-re" placeholder="you@example.com" required/></div>
          <div class="lp-field"><label>Password</label><input type="password" id="lp-rp" placeholder="Min 6 characters" required minlength="6"/></div>
          <div class="lp-field"><label>Class</label>
            <select id="lp-rcls">
              <option value="">Select class (optional)</option>
              <option>1</option><option>2</option><option>3</option><option>4</option><option>5</option>
              <option>6</option><option>7</option><option>8</option><option>9</option><option>10</option><option>11</option><option>12</option>
            </select>
          </div>
          <button type="submit" class="lp-submit" id="lp-rbtn">Create Account →</button>
        </form>
        <div class="lp-alt" id="lp-alt">
          Don't have an account? <a href="#" onclick="BYTE._lpSwitch('r');return false;">Sign Up free</a>
        </div>
      </div>
    </div>`;
  }

  function _bindLoginPopup(){
    const el = document.getElementById('lp-overlay');
    el.addEventListener('click', e=>{ if(e.target===el) closeLoginPopup(); });
    document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeLoginPopup(); });
  }

  function _lpSwitch(m){
    const isL = m==='l';
    document.getElementById('lp-tl')?.classList.toggle('on', isL);
    document.getElementById('lp-tr')?.classList.toggle('on', !isL);
    const fl = document.getElementById('lp-fl');
    const fr = document.getElementById('lp-fr');
    if(fl) fl.style.display = isL ? '' : 'none';
    if(fr) fr.style.display = isL ? 'none' : '';
    const alt = document.getElementById('lp-alt');
    if(alt) alt.innerHTML = isL
      ? `Don't have an account? <a href="#" onclick="BYTE._lpSwitch('r');return false;">Sign Up free</a>`
      : `Already have an account? <a href="#" onclick="BYTE._lpSwitch('l');return false;">Login</a>`;
    const gerr = document.getElementById('lp-gerr');
    if(gerr) gerr.classList.remove('on');
  }

  function _lpErr(m){ const e=document.getElementById('lp-gerr'); if(e){e.textContent=m;e.classList.add('on');} }

  async function _lpLogin(e){
    e.preventDefault();
    const btn=document.getElementById('lp-lbtn');
    btn.disabled=true; btn.textContent='Logging in…';
    const d=await api('/auth/login',{method:'POST',body:JSON.stringify({
      email:document.getElementById('lp-le').value,
      password:document.getElementById('lp-lp').value
    })});
    btn.disabled=false; btn.textContent='Login →';
    if(d?.success){
      auth.set(d.access_token, d.refresh_token);
      toast('Welcome back! 🎉');
      closeLoginPopup();
      api('/settings').then(s=>{ _student = s?.settings||{}; updateNav(); });
      if(_afterLogin){ const cb=_afterLogin; _afterLogin=null; setTimeout(cb, 400); }
    } 
    else { setTimeout(()=>{ const p=window.location.pathname; if(p==='/login/'||p==='/login') window.location='/learn/'; },400); }
    }
  

  async function _lpRegister(e){
    e.preventDefault();
    const btn=document.getElementById('lp-rbtn');
    btn.disabled=true; btn.textContent='Creating account…';
    const d=await api('/auth/register',{method:'POST',body:JSON.stringify({
      name:document.getElementById('lp-rn').value,
      email:document.getElementById('lp-re').value,
      password:document.getElementById('lp-rp').value,
      class:document.getElementById('lp-rcls').value,
      role:'student'
    })});
    btn.disabled=false; btn.textContent='Create Account →';
    if(d?.success){
      auth.set(d.access_token, d.refresh_token);
      toast('Account created! Welcome 🎉');
      closeLoginPopup();
      api('/settings').then(s=>{ _student = s?.settings||{}; updateNav(); });
      if(_afterLogin){ const cb=_afterLogin; _afterLogin=null; setTimeout(cb, 400); }
    } else {
      _lpErr(d?.error||'Registration failed. Try again.');
    }
  }

  // ── FOOTER ──
  function footer(){
    return `<footer class="b-footer"><strong>BYTE</strong> by EduSaint &nbsp;·&nbsp; <a href="/home/">Home</a> &nbsp;·&nbsp; <a href="/learn/">Courses</a></footer>`;
  }

  // ── INIT ──
  document.addEventListener('DOMContentLoaded', ()=>{ updateNav(); });

  return { api, auth, slug, unslug, pathParts, col, icon, cemoji, esc, toast, spinner, empty, setMeta, nav, updateNav, logout, footer, openInApp, showLoginPopup, closeLoginPopup, closeModal, _lpSwitch, _lpLogin, _lpRegister, showAppPrompt };
})();