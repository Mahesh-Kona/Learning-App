"""
WSGI entry point for production (cPanel / mod_wsgi / passenger).
Optimized version for better performance.
"""
import os
import logging
import sys
from datetime import datetime
try:
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:  # Fallback if python-dotenv isn't installed
    def load_dotenv(*args, **kwargs):  # type: ignore
        """No-op fallback when python-dotenv is unavailable."""
        return False
# Load environment variables from .env (if present) before creating the app
load_dotenv()
# Start timing - helps identify slow initialization
start_time = datetime.now()
# Add project root to path first
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Configure logging
logging.basicConfig(
    stream=sys.stderr, 
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)
# Environment settings
FLASK_ENV = os.environ.get("FLASK_ENV", "production")
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
CONFIG_OBJECT = os.environ.get("FLASK_CONFIG")
logger.info("WSGI starting (FLASK_ENV=%s, DEBUG=%s)", FLASK_ENV, DEBUG)
try:
    # Import and create app
    from app import create_app
    
    if CONFIG_OBJECT:
        module_name, _, class_name = CONFIG_OBJECT.rpartition(".")
        if module_name:
            module = __import__(module_name, fromlist=[class_name])
            config_class = getattr(module, class_name)
            application = create_app(config_class)
        else:
            application = create_app()
    else:
        application = create_app()
        
    # Log initialization time
    init_time = (datetime.now() - start_time).total_seconds()
    logger.info("WSGI app initialized in %.2f seconds", init_time)
    
except Exception as e:
    logger.exception("Failed to create Flask app: %s", e)
    raise

app = application

# ─────────────────────────────────────────────────────────
# BYTE FRONTEND STATIC ROUTES
# Serve HTML pages for clean URLs — added below existing app
# Kuch bhi existing nahi toot raha, sirf naye routes add hain
# ─────────────────────────────────────────────────────────
from flask import send_from_directory

_BASE = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
@app.route('/home/')
@app.route('/home')
def _serve_home():
    return send_from_directory(os.path.join(_BASE, 'home'), 'index.html')

@app.route('/admin-login')
@app.route('/admin-login/')
def _serve_admin_login():
    # Redirect to the actual Flask admin login page (Blueprint route)
    from flask import redirect, url_for
    return redirect('/admin/login')

@app.route('/login/')
@app.route('/login')
def _serve_login():
    return send_from_directory(os.path.join(_BASE, 'login'), 'index.html')

@app.route('/profile/')
@app.route('/profile')
def _serve_profile():
    return send_from_directory(os.path.join(_BASE, 'profile'), 'index.html')

@app.route('/learn/')
@app.route('/learn')
def _serve_learn():
    return send_from_directory(os.path.join(_BASE, 'learn'), 'index.html')

@app.route('/learn/<path:subpath>')
def _serve_learn_pages(subpath):
    parts = subpath.strip('/').split('/')
    n = len(parts)
    if n >= 4:
        fname = 'topic.html'
    elif n == 3:
        fname = 'lesson.html'
    elif n == 2:
        fname = 'course.html'
    else:
        fname = 'index.html'
    return send_from_directory(os.path.join(_BASE, 'learn'), fname)

@app.route('/assets/<path:filename>')
def _serve_assets(filename):
    return send_from_directory(os.path.join(_BASE, 'assets'), filename)

# ─────────────────────────────────────────────────────────
# SITEMAP + ROBOTS — auto-generated from DB
# byte.edusaint.in/sitemap.xml
# ─────────────────────────────────────────────────────────
from flask import Response as _Response
from datetime import date as _date
import re as _re

def _slug(s):
    s = str(s).lower()
    s = _re.sub(r'[^a-z0-9\s-]', '', s).strip()
    s = _re.sub(r'[\s-]+', '-', s)
    return s

def _url(loc, priority='0.5', changefreq='monthly', today=None):
    today = today or _date.today().isoformat()
    return f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>"""

@app.route('/sitemap.xml')
def _serve_sitemap():
    BASE = 'https://byte.edusaint.in'
    TODAY = _date.today().isoformat()
    urls = []

    # Static pages
    urls.append(_url(f'{BASE}/',        '1.0', 'weekly',  TODAY))
    urls.append(_url(f'{BASE}/home/',   '0.9', 'weekly',  TODAY))
    urls.append(_url(f'{BASE}/learn/',  '0.9', 'weekly',  TODAY))

    # Dynamic pages from DB
    try:
        from app.models import Course, Lesson, Topic

        courses = Course.query.all()
        for course in courses:
            # Skip unpublished if field exists
            try:
                if course.published == False:
                    continue
            except Exception:
                pass

            cls  = _slug(str(course.class_name or ''))
            c    = _slug(str(course.title or ''))
            cid  = course.id
            if not cls or not c:
                continue

            urls.append(_url(f'{BASE}/learn/{cls}/{c}/', '0.8', 'weekly', TODAY))

            # Lessons
            try:
                lessons = Lesson.query.filter_by(course_id=cid).all()
            except Exception:
                lessons = []

            for lesson in lessons:
                l = _slug(str(lesson.title or ''))
                lid = lesson.id
                if not l:
                    continue
                urls.append(_url(f'{BASE}/learn/{cls}/{c}/{l}/', '0.7', 'weekly', TODAY))

                # Topics
                try:
                    topics = Topic.query.filter_by(lesson_id=lid).all()
                except Exception:
                    topics = []

                for topic in topics:
                    t = _slug(str(topic.title or ''))
                    if not t:
                        continue
                    urls.append(_url(f'{BASE}/learn/{cls}/{c}/{l}/{t}/', '0.6', 'monthly', TODAY))

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('Sitemap DB error: %s', e)

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>'

    return _Response(xml, mimetype='application/xml')


@app.route('/robots.txt')
def _serve_robots():
    txt = """User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /admin-login/

Sitemap: https://byte.edusaint.in/sitemap.xml"""
    return _Response(txt, mimetype='text/plain')