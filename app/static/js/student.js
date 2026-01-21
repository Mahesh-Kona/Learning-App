// Base URL for API calls; override by setting window.API_BASE (e.g., 'http://127.0.0.1:5000')
// Prefer explicit API_BASE; otherwise fall back to current origin. This prevents HTTP 0 when
// the page is opened from file:// or a different host/port.
const API_BASE = window.API_BASE || `${window.location.origin}`;

// Students data will be fetched from API endpoint /api/v1/students
let studentsData = [];

// Leaderboard will be fetched from API endpoint /api/v1/leaderboard
let leaderboardData = [];

let selectedStudents = new Set();
let currentFilter = { search: '', status: '', course: '' };

const studentTableBody = document.getElementById('studentTableBody');
const selectAllCheckbox = document.getElementById('selectAll');
const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const courseFilter = document.getElementById('courseFilter');
const applyFilterBtn = document.getElementById('applyFilterBtn');
const clearFiltersBtn = document.getElementById('clearFiltersBtn');
const leaderboardTableBody = document.getElementById('leaderboardTableBody');
const totalStudentsCount = document.getElementById('totalStudentsCount');
const activeThisWeekCount = document.getElementById('activeThisWeekCount');
const newThisMonthCount = document.getElementById('newThisMonthCount');
const studentModal = document.getElementById('studentModal');
const modalTitle = document.getElementById('modalTitle');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalCancelBtn = document.getElementById('modalCancelBtn');
const modalSaveBtn = document.getElementById('modalSaveBtn');
const modalForm = document.getElementById('studentForm');
const modalName = document.getElementById('modalName');
const modalEmail = document.getElementById('modalEmail');
const modalMobile = document.getElementById('modalMobile');
const modalEnrollment = document.getElementById('modalEnrollment');
const modalCourses = document.getElementById('modalCourses');
const modalStatus = document.getElementById('modalStatus');
const exportBtn = document.getElementById('exportBtn');
const addStudentBtn = document.getElementById('addStudentBtn');
const refreshLeaderboardBtn = document.getElementById('refreshLeaderboardBtn');
const exportLeaderboardBtn = document.getElementById('exportLeaderboardBtn');
// Rich Add Student modal elements
const addStudentModal = document.getElementById('addStudentModal');
const addStudentCloseBtn = document.getElementById('addStudentCloseBtn');
const addStudentCancelBtn = document.getElementById('addStudentCancelBtn');
const addStudentSubmitBtn = document.getElementById('addStudentSubmitBtn');
const addStudentSuccessMessage = document.getElementById('addStudentSuccessMessage');
const addStudentFormEl = document.getElementById('addStudentForm');
const courseModalOverlay = document.getElementById('courseModalOverlay');
const courseModal = document.getElementById('courseModal');
const courseLevelSelect = document.getElementById('courseLevel');
const subjectNameSelect = document.getElementById('subjectName');
const selectedCoursesList = document.getElementById('selectedCoursesList');
const courseCountEl = document.getElementById('courseCount');
const passwordInput = document.getElementById('studentPassword');
const passwordStrengthEl = document.getElementById('passwordStrength');
const strengthFillEl = document.getElementById('strengthFill');
const photoPreviewEl = document.getElementById('photoPreview');
// Rich Edit Student modal elements (in-page)
const editStudentModal = document.getElementById('editStudentModal');
const editStudentCloseBtn = document.getElementById('editStudentCloseBtn');
const editStudentCancelBtn = document.getElementById('editStudentCancelBtn');
const editStudentSaveBtn = document.getElementById('editStudentSaveBtn');
const editStudentSuccessMessage = document.getElementById('editStudentSuccessMessage');
const editStudentFormEl = document.getElementById('editStudentForm');
const editSelectedCoursesList = document.getElementById('editSelectedCoursesList');
const editCourseCountEl = document.getElementById('editCourseCount');
const editPhotoPreviewEl = document.getElementById('editPhotoPreview');
let editingStudentId = null;

// Fetch and store JWT token for API calls
let jwtToken = null;

// State for Add Student modal
let addPasswordVisible = false;
let addSelectedCourses = [];

// State for Edit Student modal
let editingRichStudentId = null;
let editSelectedCourses = [];

// Course modal context: controls whether Add Course updates addSelectedCourses or editSelectedCourses
let courseModalContext = 'add';

// Edit password UI state
let editPasswordVisible = false;

// Cache of courses per class_id loaded from backend
// Shape: { [classId: string]: Array<{ id, title, class_name, category, ... }> }
const classCoursesCache = {};

document.addEventListener('DOMContentLoaded', () => {
  // Fetch JWT token first, then load data (only on pages that have the relevant sections)
  fetchJWTToken().then(() => {
    if (studentTableBody) {
      fetchAndRenderStudents();
    }
    if (leaderboardTableBody) {
      fetchAndRenderLeaderboard();
    }
    attachEventListeners();

    // If coming from a page with ?open_add=1, auto-open Add Student modal
    try {
      const params = new URLSearchParams(window.location.search || '');
      const openAdd = params.get('open_add');
      if (openAdd && openAdd !== '0' && openAdd.toLowerCase() !== 'false') {
        openAddModal();
      }
    } catch (e) {
      console.error('Failed to parse query params for open_add:', e);
    }
  });
});

/**
 * Fetch JWT token from admin session
 */
async function fetchJWTToken() {
  try {
    // Try to get from localStorage first
    jwtToken = localStorage.getItem('admin_jwt_token');
    if (jwtToken) return;
    
    // Otherwise fetch from server
    const res = await fetch(`${API_BASE}/admin/api/get-jwt-token`, {
      credentials: 'include'  // Include session cookies
    });
    
    if (res.ok) {
      const data = await res.json();
      if (data.success && data.access_token) {
        jwtToken = data.access_token;
        // Cache it in localStorage
        localStorage.setItem('admin_jwt_token', jwtToken);
      }
    }
  } catch (err) {
    console.error('Failed to fetch JWT token:', err);
  }
}

/**
 * Ensure we have a valid JWT loaded in memory.
 * Tries localStorage, then fetches from admin endpoint.
 */
async function ensureJWT() {
  if (jwtToken) return jwtToken;
  const cached = localStorage.getItem('admin_jwt_token');
  if (cached) { jwtToken = cached; return jwtToken; }
  await fetchJWTToken();
  return jwtToken;
}

/**
 * Safely parse a fetch Response as JSON when possible; otherwise return text.
 * Returns { json, text, contentType }
 */
async function parseJSONOrText(res) {
  const contentType = (res.headers && res.headers.get && res.headers.get('content-type')) || '';
  if (contentType.includes('application/json')) {
    try {
      const j = await res.json();
      return { json: j, text: null, contentType };
    } catch (e) {
      // Fallback to text if JSON parse fails
      try {
        const t = await res.text();
        return { json: null, text: t, contentType };
      } catch (_) {
        return { json: null, text: null, contentType };
      }
    }
  }
  try {
    const t = await res.text();
    return { json: null, text: t, contentType };
  } catch (_) {
    return { json: null, text: null, contentType };
  }
}

/**
 * Fetch students from /api/v1/students endpoint and render table
 */
function fetchAndRenderStudents() {
  fetch(`${API_BASE}/api/v1/students?limit=100`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      studentsData = (data.students || []).map(s => ({
        id: s.id,
        name: s.name || 'Unknown',
        email: s.email || '',
        enrollmentDate: s.enrollmentDate || '',
        mobile: s.mobile || '',
        image: s.image || '',
        class: s.class || '',
        syllabus: s.syllabus || '',
        courses: s.courses || '',
        progress: s.progress || 0,
        xp: s.xp || 0,
        lastLogin: s.lastLogin || '',
        status: s.status || 'active'
      }));
      renderTable(studentsData);
      updateStats(studentsData);
    })
    .catch(err => {
      console.error('Failed to fetch students:', err);
      if (studentTableBody) {
        studentTableBody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:24px;color:red;">Failed to load students</td></tr>`;
      }
    });
}

function attachEventListeners() {
  selectAllCheckbox?.addEventListener('change', handleSelectAll);
  searchInput?.addEventListener('input', handleSearch);
  clearFiltersBtn?.addEventListener('click', clearFilters);
  statusFilter?.addEventListener('change', applyFilters);
  courseFilter?.addEventListener('change', applyFilters);
  modalCloseBtn?.addEventListener('click', closeModal);
  modalCancelBtn?.addEventListener('click', closeModal);
  studentModal?.addEventListener('click', (e) => { if (e.target === studentModal) closeModal(); });
  modalForm?.addEventListener('submit', handleModalSave);
  exportBtn?.addEventListener('click', exportToCSV);
  addStudentBtn?.addEventListener('click', openAddModal);
  refreshLeaderboardBtn?.addEventListener('click', fetchAndRenderLeaderboard);
  exportLeaderboardBtn?.addEventListener('click', exportLeaderboardToCSV);
  // Rich Add Student modal events
  addStudentCloseBtn?.addEventListener('click', closeAddStudentModal);
  addStudentCancelBtn?.addEventListener('click', closeAddStudentModal);
  addStudentModal?.addEventListener('click', (e) => { if (e.target === addStudentModal) closeAddStudentModal(); });
  addStudentSubmitBtn?.addEventListener('click', submitAddStudentForm);
  courseModalOverlay?.addEventListener('click', closeCourseModal);

  // Rich Edit Student modal events
  editStudentCloseBtn?.addEventListener('click', closeEditStudentModal);
  editStudentCancelBtn?.addEventListener('click', closeEditStudentModal);
  editStudentModal?.addEventListener('click', (e) => { if (e.target === editStudentModal) closeEditStudentModal(); });
  editStudentSaveBtn?.addEventListener('click', submitEditStudentForm);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (courseModal && courseModal.classList.contains('active')) {
        closeCourseModal();
      } else if (editStudentModal && !editStudentModal.classList.contains('hidden')) {
        closeEditStudentModal();
      } else if (addStudentModal && !addStudentModal.classList.contains('hidden')) {
        closeAddStudentModal();
      }
    }
  });
}

function renderTable(data) {
  studentTableBody.innerHTML = '';
  if (!data.length) {
    studentTableBody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:24px;">No students found</td></tr>`;
    return;
  }
  data.forEach(student => studentTableBody.appendChild(createStudentRow(student)));
  animateProgressBars();
  updateSelectAllCheckbox();
  updateSelectedCount();
}

function createStudentRow(student) {
  const tr = document.createElement('tr');
  const statusClass = student.status === 'active' ? 'status-active' : 'status-inactive';
  const studentEmail = student.email || `student${student.id}@email.com`;
  const coursesDisplay = sanitizeCoursesForDisplay(student.courses || '');
  tr.innerHTML = `
    <td><input type="checkbox" class="student-checkbox" data-id="${student.id}" onchange="handleCheckbox('${student.id}')"></td>
    <td>${student.id}</td>
    <td><strong>${student.name}</strong></td>
    <td>${studentEmail}</td>
    <td>${formatDate(student.enrollmentDate)}</td>
    <td>${coursesDisplay}</td>
    <td>
      <div class="progress-wrapper">
        <div class="progress-bar">
          <div class="progress-fill" data-progress="${student.progress}"></div>
        </div>
        <span>${student.progress}%</span>
      </div>
    </td>
    <td><span class="status-badge ${statusClass}">${student.status}</span></td>
    <td>
      <div class="action-btns">
        <i class="ri-eye-line" title="View" onclick="viewStudent('${student.id}')"></i>
        <i class="ri-pencil-line" title="Edit" onclick="editStudent('${student.id}')"></i>
        <i class="ri-chat-1-line" title="Message" onclick="messageStudent('${student.id}')"></i>
        <i class="ri-delete-bin-6-line" title="Delete" onclick="removeStudent('${student.id}')"></i>
      </div>
    </td>
  `;
  return tr;
}

function sanitizeCourseName(name) {
  const raw = String(name || '').trim();
  if (!raw) return '';
  return raw
    .replace(/\(\s*Class\s*\d+\s*\)/ig, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function sanitizeCoursesForDisplay(coursesString) {
  const raw = String(coursesString || '').trim();
  if (!raw) return '';
  // Display should be clean even if DB has legacy entries like "English (Class 10)".
  const names = raw
    .split(',')
    .map(s => sanitizeCourseName(s))
    .filter(Boolean);
  return names.join(', ');
}

function coursesArrayToDbString(courses, fallbackClass) {
  const list = Array.isArray(courses) ? courses : [];
  const seen = new Set();
  const names = [];
  for (const c of list) {
    const normalized = normalizeCourseEntry(c, fallbackClass);
    const clean = sanitizeCourseName(normalized.name);
    if (!clean) continue;
    const key = clean.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    names.push(clean);
  }
  return names.join(', ');
}

function showFeedback(message, type = 'success') {
  const text = String(message || '').trim();
  if (!text) return;

  let container = document.getElementById('feedbackToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'feedbackToastContainer';
    container.style.position = 'fixed';
    container.style.top = '16px';
    container.style.right = '16px';
    container.style.zIndex = '99999';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.gap = '10px';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const bg = (type === 'error') ? '#d64545' : (type === 'warning') ? '#d98b2b' : '#1f9d55';
  toast.textContent = text;
  toast.style.background = bg;
  toast.style.color = '#fff';
  toast.style.padding = '10px 12px';
  toast.style.borderRadius = '10px';
  toast.style.boxShadow = '0 10px 22px rgba(0,0,0,0.18)';
  toast.style.maxWidth = '360px';
  toast.style.fontSize = '14px';
  toast.style.lineHeight = '1.3';
  toast.style.opacity = '0';
  toast.style.transform = 'translateY(-6px)';
  toast.style.transition = 'opacity 160ms ease, transform 160ms ease';
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  });

  window.setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-6px)';
    window.setTimeout(() => toast.remove(), 200);
  }, 2400);
}


/**
 * Fetch leaderboard from /api/v1/leaderboard endpoint and render table
 */
function fetchAndRenderLeaderboard() {
  fetch(`${API_BASE}/api/v1/leaderboard?limit=50`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      leaderboardData = data.leaderboard || [];
      renderLeaderboard(leaderboardData);
    })
    .catch(err => {
      console.error('Failed to fetch leaderboard:', err);
      if (leaderboardTableBody) {
        leaderboardTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:red;">Failed to load leaderboard</td></tr>`;
      }
    });
}

function renderLeaderboard(data) {
  if (!leaderboardTableBody) return;
  leaderboardTableBody.innerHTML = '';
  if (!data.length) {
    leaderboardTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;">No data</td></tr>`;
    return;
  }
  data.forEach(entry => {
    const name = entry.name || entry.email || 'Unknown';
    const score = entry.score || 0;
    const lastUpdated = formatDate(entry.last_updated_date) || '';
    const statusClass = entry.status === 'active' ? 'status-active' : 'status-inactive';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${entry.rank}</td>
      <td>${name}</td>
      <td>${score}</td>
      <td>${lastUpdated}</td>
      <td><span class="status-badge ${statusClass}">${entry.status}</span></td>
    `;
    leaderboardTableBody.appendChild(tr);
  });
}


function animateProgressBars() {
  document.querySelectorAll('.progress-fill').forEach(bar => {
    const width = bar.getAttribute('data-progress');
    bar.style.width = "0%";
    setTimeout(() => { bar.style.transition = "width 0.6s ease"; bar.style.width = width + "%"; }, 50);
  });
}

function handleCheckbox(id) {
  const box = document.querySelector(`input[data-id="${id}"]`);
  box.checked ? selectedStudents.add(id) : selectedStudents.delete(id);
  updateSelectAllCheckbox();
  updateSelectedCount();
}
window.handleCheckbox = handleCheckbox;

function handleSelectAll(e) {
  const checked = e.target.checked;
  document.querySelectorAll('.student-checkbox').forEach(cb => {
    cb.checked = checked;
    checked ? selectedStudents.add(cb.dataset.id) : selectedStudents.delete(cb.dataset.id);
  });
  updateSelectedCount();
}

function updateSelectAllCheckbox() {
  const boxes = document.querySelectorAll('.student-checkbox');
  if (!boxes.length) return;
  const checked = Array.from(boxes).filter(cb => cb.checked);
  selectAllCheckbox.checked = checked.length === boxes.length;
  selectAllCheckbox.indeterminate = checked.length > 0 && checked.length < boxes.length;
}

function updateSelectedCount() {
  const count = document.querySelector('.selected-count');
  if (count) count.textContent = `${selectedStudents.size} selected`;
}

function updateStats(data) {
  const total = data.length;
  const now = new Date();
  const msInDay = 24 * 60 * 60 * 1000;

  let activeWeek = 0;
  let newMonth = 0;

  data.forEach(s => {
    const d = parseDateStrict(s.enrollmentDate);
    if (!d) return;
    const diffDays = (now - d) / msInDay;
    if (diffDays >= 0 && diffDays <= 7) activeWeek += 1;
    if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) newMonth += 1;
  });

  if (totalStudentsCount) totalStudentsCount.textContent = total;
  if (activeThisWeekCount) activeThisWeekCount.textContent = activeWeek;
  if (newThisMonthCount) newThisMonthCount.textContent = newMonth;
}

function handleSearch(e) { currentFilter.search = e.target.value.toLowerCase(); applyFilters(); }
function applyFilters() {
  currentFilter.status = (statusFilter.value || '').toLowerCase();
  currentFilter.course = (courseFilter.value || '').toLowerCase();
  const filtered = studentsData.filter(s => {
    const sname = (s.name || '').toLowerCase();
    const sid = String(s.id || '').toLowerCase();
    const semail = (s.email || '').toLowerCase();
    const scourses = (s.courses || '').toLowerCase();
    const matchSearch = !currentFilter.search || sname.includes(currentFilter.search) || sid.includes(currentFilter.search) || semail.includes(currentFilter.search) || scourses.includes(currentFilter.search);
    const matchStatus = !currentFilter.status || (s.status || '').toLowerCase() === currentFilter.status;
    const matchCourse = !currentFilter.course || scourses.includes(currentFilter.course);
    return matchSearch && matchStatus && matchCourse;
  });
  selectedStudents.clear();
  renderTable(filtered);
}
function clearFilters() {
  searchInput.value = ""; statusFilter.value = ""; courseFilter.value = "";
  currentFilter = { search: '', status: '', course: '' };
  selectedStudents.clear();
  renderTable(studentsData);
}


function viewStudent(id) {
  // Navigate to the admin student detail page
  try {
    const base = window.API_BASE || window.location.origin;
    const url = `${base}/admin/students/${id}`;
    window.location.href = url;
  } catch (e) {
    console.error('Failed to navigate to student detail:', e);
  }
}

function editStudent(id) {
  (async () => {
    // Prefer fetching detail for more complete fields
    try {
      const res = await fetch(`${API_BASE}/api/v1/students/${id}`, { credentials: 'include' });
      if (res.ok) {
        const detail = await res.json();
        const s = detail.student || detail;
        openEditStudentModal({
          id: s.id,
          name: s.name || '',
          email: s.email || '',
          mobile: s.mobile || '',
          class: s.class || s.class_ || '',
          syllabus: s.syllabus || '',
          enrollmentDate: s.enrollmentDate || '',
          status: (s.status || 'active'),
          courses: s.courses || '',
          image: s.image || ''
        });
        return;
      }
    } catch (e) {
      console.warn('Failed to fetch student detail for rich edit modal. Falling back to list data.', e);
    }

    const s = findStudent(id);
    if (!s) return alert('Student not found');
    openEditStudentModal({
      id: s.id,
      name: s.name || '',
      email: s.email || '',
      mobile: s.mobile || '',
      class: s.class || '',
      syllabus: s.syllabus || '',
      enrollmentDate: s.enrollmentDate || '',
      status: (s.status || 'active'),
      courses: s.courses || '',
      image: s.image || ''
    });
  })();
}

function messageStudent(id) {
  const s = findStudent(id);
  if (!s) return alert('Student not found');
  const msg = prompt(`Message to ${s.name || 'student'}:`, 'Hello!');
  if (msg) alert('Message queued: ' + msg);
}

async function removeStudent(id) {
  const s = findStudent(id);
  if (!s) return alert('Student not found');
  if (!confirm(`Remove ${s.name || 'student'}?`)) return;

  try {
    const token = await ensureJWT();
    if (!token) {
      alert('Authentication required. Please login as admin and retry.');
      return;
    }

    const doDelete = async (bearer) => {
      const res = await fetch(`${API_BASE}/api/v1/students/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${bearer}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });
      const parsed = await parseJSONOrText(res);
      return { res, parsed };
    };

    const doFallbackDeletePost = async (bearer) => {
      const res = await fetch(`${API_BASE}/api/v1/students/${id}/delete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${bearer}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });
      const parsed = await parseJSONOrText(res);
      return { res, parsed };
    };

    // First attempt
    let { res, parsed } = await doDelete(token);

    // If unauthorized/forbidden, refresh token once via admin endpoint and retry
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem('admin_jwt_token');
      jwtToken = null;
      await fetchJWTToken();
      const refreshed = jwtToken;
      if (!refreshed) {
        alert('Unauthorized. Please re-login as admin.');
        return;
      }
      ({ res, parsed } = await doDelete(refreshed));
    }

    // If still 403 and response is non-JSON (likely upstream 403 page), try POST fallback
    if (res.status === 403 && (!parsed.json) && parsed.text && parsed.text.trim().startsWith('<')) {
      console.warn('DELETE blocked upstream (HTML 403). Retrying via POST fallback...');
      const bearer = jwtToken || localStorage.getItem('admin_jwt_token');
      if (!bearer) {
        alert('Unauthorized. Please re-login as admin.');
        return;
      }
      ({ res, parsed } = await doFallbackDeletePost(bearer));
    }

    if (res.ok && parsed.json && parsed.json.success) {
      const index = studentsData.findIndex(st => String(st.id) === String(id));
      if (index > -1) studentsData.splice(index, 1);
      applyFilters();
      updateStats(studentsData);
      alert('Student deleted successfully');
      return;
    }

    // Build a clearer error message
    const statusPart = `HTTP ${res.status}`;
    const apiError = (parsed.json && (parsed.json.error || parsed.json.message)) || null;
    const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
    const details = apiError || textSnippet || 'Unknown error';

    if (parsed.text && parsed.text.trim().startsWith('<')) {
      console.warn('Non-JSON error response body (truncated):', parsed.text.substring(0, 1000));
    }

    alert(`Failed to delete: ${statusPart} - ${details}`);
  } catch (err) {
    console.error('Delete failed:', err);
    alert('Failed to delete student');
  }
}

function findStudent(id) {
  return studentsData.find(st => String(st.id) === String(id));
}

function openEditModal(student) {
  editingStudentId = student.id;
  modalTitle.textContent = 'Edit Student';
  modalName.value = student.name || '';
  modalEmail.value = student.email || '';
  modalMobile.value = student.mobile || '';
  modalEnrollment.value = student.enrollmentDate || '';
  modalCourses.value = student.courses || '';
  modalStatus.value = (student.status || 'active');
  studentModal.classList.remove('hidden');
}

function openAddModal() {
  // Use the rich Add Student modal instead of the simple form
  courseModalContext = 'add';
  resetAddStudentForm();
  if (addStudentModal) {
    addStudentModal.classList.remove('hidden');
  }
}

function parseCoursesString(coursesString) {
  const raw = String(coursesString || '').trim();
  if (!raw) return [];
  // Accept older/messy formats too, e.g. "English (Class 10) (Class 10)".
  // Extract the last class marker if present, and strip all class markers from the name.
  return raw.split(',').map(s => s.trim()).filter(Boolean).map(item => {
    const classMatches = Array.from(item.matchAll(/\(\s*Class\s*(\d+)\s*\)/ig));
    const classVal = classMatches.length ? String(classMatches[classMatches.length - 1][1] || '').trim() : '';
    const nameClean = String(item).replace(/\(\s*Class\s*\d+\s*\)/ig, '').replace(/\s{2,}/g, ' ').trim();
    return { class: classVal, id: '', name: nameClean || item };
  });
}

function normalizeCourseEntry(course, fallbackClass) {
  const nameRaw = (course && course.name != null) ? String(course.name) : '';
  const classRaw = (course && course.class != null) ? String(course.class) : '';
  const nameClean = nameRaw.replace(/\(\s*Class\s*\d+\s*\)/ig, '').replace(/\s{2,}/g, ' ').trim();
  const classClean = classRaw.trim() || (fallbackClass ? String(fallbackClass).trim() : '');
  return {
    name: nameClean || nameRaw.trim(),
    class: classClean
  };
}

function resetEditStudentForm() {
  editingRichStudentId = null;
  editSelectedCourses = [];
  if (editStudentSuccessMessage) {
    editStudentSuccessMessage.style.display = 'none';
  }

  // Reset password management controls (Edit modal)
  editPasswordVisible = false;
  const newPwEl = document.getElementById('editNewPassword');
  if (newPwEl) {
    newPwEl.value = '';
    newPwEl.type = 'password';
  }
  const strengthEl = document.getElementById('editPasswordStrength');
  if (strengthEl) strengthEl.className = 'password-strength';
  const fillEl = document.getElementById('editStrengthFill');
  if (fillEl) fillEl.style.width = '0%';
  const toggleBtn = editStudentModal ? editStudentModal.querySelector('.password-toggle') : null;
  if (toggleBtn) toggleBtn.textContent = '👁️';

  if (editPhotoPreviewEl) {
    editPhotoPreviewEl.innerHTML = '<span class="photo-preview-icon">👤</span>';
  }
  const fileInput = document.getElementById('editProfilePhoto');
  if (fileInput) fileInput.value = '';
  editStudentFormEl?.reset();
  courseModalContext = 'edit';
  updateCoursesList();
}

function openEditStudentModal(student) {
  resetEditStudentForm();
  editingRichStudentId = student.id;
  courseModalContext = 'edit';

  const nameEl = document.getElementById('editStudentName');
  const emailEl = document.getElementById('editEmail');
  const phoneEl = document.getElementById('editPhone');
  const classEl = document.getElementById('editStudentClass');
  const boardEl = document.getElementById('editBoard');
  const enrollEl = document.getElementById('editEnrollmentDate');
  const statusEl = document.getElementById('editStatus');

  if (nameEl) nameEl.value = student.name || '';
  if (emailEl) emailEl.value = student.email || '';
  if (phoneEl) phoneEl.value = student.mobile || '';
  if (classEl) classEl.value = String(student.class || '').trim();
  if (boardEl) boardEl.value = String(student.syllabus || '').trim();
  if (enrollEl) enrollEl.value = (student.enrollmentDate || '').slice(0, 10);
  if (statusEl) statusEl.value = (String(student.status || 'active').toLowerCase() === 'inactive') ? 'inactive' : 'active';

  if (editPhotoPreviewEl) {
    const img = (student.image || '').trim();
    if (img) {
      const fallbackSrc = img.startsWith('http') ? img : `${API_BASE}${img.startsWith('/') ? '' : '/'}${img}`;
      // Prefer the avatar-serving endpoint. In many deployments, /avatars/... is not a public route,
      // while /api/v1/students/<id>/avatar is.
      const avatarSrc = `${API_BASE}/api/v1/students/${student.id}/avatar?t=${Date.now()}`;
      const primarySrc = img.startsWith('http') ? img : avatarSrc;
      editPhotoPreviewEl.innerHTML = `
        <img
          src="${primarySrc}"
          alt="Profile"
          onerror="this.onerror=null; this.src='${fallbackSrc}';"
        >
      `;
    }
  }

  editSelectedCourses = parseCoursesString(student.courses || '');
  // Backfill missing class markers from student's current class to avoid "(Class )".
  const fallbackClass = String(student.class || '').trim();
  if (fallbackClass) {
    editSelectedCourses = editSelectedCourses.map(c => ({
      ...c,
      class: (String(c.class || '').trim() || fallbackClass)
    }));
  }
  updateCoursesList();

  if (editStudentModal) {
    editStudentModal.classList.remove('hidden');
  }
}

function closeEditStudentModal() {
  if (editStudentModal) editStudentModal.classList.add('hidden');
  resetEditStudentForm();
}

function exportToCSV() {
  if (!studentsData.length) return alert('No data to export');
  const headers = ['ID', 'Name', 'Email', 'Enrollment Date', 'Courses', 'Status'];
  const rows = studentsData.map(s => [
    s.id,
    s.name || '',
    s.email || '',
    s.enrollmentDate || '',
    s.courses || '',
    s.status || ''
  ]);
  const csvContent = [headers, ...rows].map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `students_${new Date().toISOString().split('T')[0]}.csv`;
  link.click();
}

function exportLeaderboardToCSV() {
  if (!leaderboardData.length) return alert('No leaderboard data to export');
  const headers = ['Rank', 'Name', 'Email', 'Score', 'League', 'Last Updated', 'Status'];
  const rows = leaderboardData.map(entry => [
    entry.rank || '',
    entry.name || '',
    entry.email || '',
    entry.score || '',
    entry.league || '',
    entry.last_updated_date || '',
    entry.status || ''
  ]);
  const csvContent = [headers, ...rows].map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `leaderboard_${new Date().toISOString().split('T')[0]}.csv`;
  link.click();
}

function closeModal() {
  editingStudentId = null;
  studentModal.classList.add('hidden');
}

function resetAddStudentForm() {
  if (!addStudentFormEl) return;
  addStudentFormEl.reset();
  if (photoPreviewEl) {
    photoPreviewEl.innerHTML = '<span class="photo-preview-icon">👤</span>';
  }
  if (addStudentSuccessMessage) {
    addStudentSuccessMessage.style.display = 'none';
  }
  if (passwordStrengthEl && strengthFillEl) {
    passwordStrengthEl.className = 'password-strength';
    strengthFillEl.style.width = '0%';
  }
  addSelectedCourses = [];
  updateCoursesList();
}

function closeAddStudentModal() {
  if (addStudentModal) {
    addStudentModal.classList.add('hidden');
  }
  resetAddStudentForm();
}

function validateAndPreviewPhoto(event) {
  const file = event.target.files && event.target.files[0];
  const maxSize = 100 * 1024; // 100 KB
  const allowedTypes = ['image/jpeg', 'image/png', 'image/jpg'];

  if (!file) return;

  if (!allowedTypes.includes(file.type)) {
    alert('⚠️ Invalid file type!\n\nOnly JPEG and PNG images are allowed.');
    event.target.value = '';
    return;
  }

  if (file.size > maxSize) {
    const fileSizeKB = (file.size / 1024).toFixed(2);
    alert(`⚠️ File too large!\n\nYour file is ${fileSizeKB} KB.\nMaximum allowed size is 100 KB.`);
    event.target.value = '';
    return;
  }

  const reader = new FileReader();
  reader.onload = function (e) {
    const inputId = (event && event.target && event.target.id) ? event.target.id : '';
    const preview = (inputId === 'editProfilePhoto') ? editPhotoPreviewEl : photoPreviewEl;
    if (preview) preview.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
  };
  reader.readAsDataURL(file);
}

function openCourseModal(context) {
  courseModalContext = (context === 'edit') ? 'edit' : 'add';
  if (!courseModalOverlay || !courseModal) return;
  courseModalOverlay.classList.add('active');
  courseModal.classList.add('active');
  if (courseLevelSelect) courseLevelSelect.value = '';
  if (subjectNameSelect) {
    subjectNameSelect.disabled = true;
    subjectNameSelect.innerHTML = '<option value="">First select a class</option>';
  }
}

function closeCourseModal() {
  if (!courseModalOverlay || !courseModal) return;
  courseModalOverlay.classList.remove('active');
  courseModal.classList.remove('active');
}

async function loadCourses() {
  if (!courseLevelSelect || !subjectNameSelect) return;
  const classValue = courseLevelSelect.value;
  if (!classValue) {
    subjectNameSelect.disabled = true;
    subjectNameSelect.innerHTML = '<option value="">First select a class</option>';
    return;
  }

  subjectNameSelect.disabled = false;
  subjectNameSelect.innerHTML = '<option value="">Loading courses...</option>';

  const populateOptions = (courses) => {
    subjectNameSelect.disabled = false;
    if (!courses || !courses.length) {
      subjectNameSelect.innerHTML = '<option value="">No courses for this class</option>';
      return;
    }
    subjectNameSelect.innerHTML = '<option value="">Select Subject</option>';
    courses.forEach(c => {
      const option = document.createElement('option');
      option.value = String(c.id);
      option.textContent = c.title || `Course ${c.id}`;
      option.dataset.className = c.class_name || '';
      subjectNameSelect.appendChild(option);
    });
  };

  // Use cache if available
  if (classCoursesCache[classValue]) {
    populateOptions(classCoursesCache[classValue]);
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/v1/classes/${classValue}/courses?limit=200`);
    if (!res.ok) {
      console.error('Failed to load class courses:', res.status);
      subjectNameSelect.innerHTML = '<option value="">Failed to load courses</option>';
      return;
    }
    const data = await res.json();
    const courses = (data && data.data) || [];
    classCoursesCache[classValue] = courses;
    populateOptions(courses);
  } catch (err) {
    console.error('Error loading class courses:', err);
    subjectNameSelect.innerHTML = '<option value="">Failed to load courses</option>';
  }
}

function addCourse() {
  if (!courseLevelSelect || !subjectNameSelect) return;
  const classValue = courseLevelSelect.value;
  const selectedOption = subjectNameSelect.options[subjectNameSelect.selectedIndex];
  const courseId = selectedOption ? selectedOption.value : '';
  const courseName = selectedOption ? selectedOption.textContent : '';

  if (!classValue || !courseName) {
    alert('⚠️ Please select both class and subject');
    return;
  }

  const targetCourses = (courseModalContext === 'edit') ? editSelectedCourses : addSelectedCourses;
  // Since we store only course names in DB, treat same-named courses as duplicates even across classes.
  const cleanName = sanitizeCourseName(courseName);
  const exists = targetCourses.some(c => sanitizeCourseName(c && c.name) && sanitizeCourseName(c.name).toLowerCase() === cleanName.toLowerCase());
  if (exists) {
    alert(`⚠️ Already Added!\n\n"${courseName}" from Class ${classValue} is already in the enrollment list.`);
    return;
  }

  targetCourses.push({ class: classValue, id: courseId, name: courseName });
  updateCoursesList();
  closeCourseModal();
}

function removeCourse(index) {
  const targetCourses = (courseModalContext === 'edit') ? editSelectedCourses : addSelectedCourses;
  targetCourses.splice(index, 1);
  updateCoursesList();
}

function updateCoursesList() {
  const isEdit = courseModalContext === 'edit';
  const listEl = isEdit ? editSelectedCoursesList : selectedCoursesList;
  const countEl = isEdit ? editCourseCountEl : courseCountEl;
  const courses = isEdit ? editSelectedCourses : addSelectedCourses;
  if (!listEl || !countEl) return;
  countEl.textContent = courses.length;

  if (!courses.length) {
    listEl.innerHTML = `
      <div class="empty-courses">
        No courses selected yet. Click "Add Course" to enroll student.
      </div>
    `;
    return;
  }

  listEl.innerHTML = courses.map((course, index) => `
    <div class="course-item">
      <div class="course-info">
        <div class="course-name">${course.name}</div>
        <div class="course-details">Class ${course.class}</div>
      </div>
      <button type="button" class="btn-remove-course" onclick="removeCourse(${index})">Remove</button>
    </div>
  `).join('');
}

function togglePassword() {
  if (!passwordInput) return;
  const toggleBtn = document.querySelector('.password-toggle');
  if (!toggleBtn) return;

  if (addPasswordVisible) {
    passwordInput.type = 'password';
    toggleBtn.textContent = '👁️';
    addPasswordVisible = false;
  } else {
    passwordInput.type = 'text';
    toggleBtn.textContent = '🙈';
    addPasswordVisible = true;
  }
}

function generatePassword() {
  if (!passwordInput) return;
  const length = 12;
  const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
  let password = '';

  password += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[Math.floor(Math.random() * 26)];
  password += 'abcdefghijklmnopqrstuvwxyz'[Math.floor(Math.random() * 26)];
  password += '0123456789'[Math.floor(Math.random() * 10)];
  password += '!@#$%^&*'[Math.floor(Math.random() * 8)];

  for (let i = password.length; i < length; i++) {
    password += charset[Math.floor(Math.random() * charset.length)];
  }

  password = password.split('').sort(() => Math.random() - 0.5).join('');

  passwordInput.value = password;
  checkPasswordStrength();

  const toggleBtn = document.querySelector('.password-toggle');
  if (toggleBtn) {
    passwordInput.type = 'text';
    toggleBtn.textContent = '🙈';
    addPasswordVisible = true;
  }
}

function autoGeneratePassword() {
  generatePassword();
  alert('Strong password generated! The password is now visible in the field.');
}

function checkPasswordStrength() {
  if (!passwordInput || !passwordStrengthEl || !strengthFillEl) return;
  const password = passwordInput.value;
  if (!password.length) {
    passwordStrengthEl.className = 'password-strength';
    strengthFillEl.style.width = '0%';
    return;
  }

  let strength = 0;
  if (password.length >= 8) strength++;
  if (password.length >= 12) strength++;
  if (/[a-z]/.test(password)) strength++;
  if (/[A-Z]/.test(password)) strength++;
  if (/[0-9]/.test(password)) strength++;
  if (/[^a-zA-Z0-9]/.test(password)) strength++;

  if (strength <= 2) {
    passwordStrengthEl.className = 'password-strength strength-weak';
  } else if (strength <= 4) {
    passwordStrengthEl.className = 'password-strength strength-medium';
  } else {
    passwordStrengthEl.className = 'password-strength strength-strong';
  }
}

function generateResetToken() {
  return 'reset_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

function sendEditPasswordReset() {
  const sendEmailEl = document.getElementById('editResetEmail');
  const sendSmsEl = document.getElementById('editResetSms');
  const sendEmail = !!(sendEmailEl && sendEmailEl.checked);
  const sendSms = !!(sendSmsEl && sendSmsEl.checked);

  if (!sendEmail && !sendSms) {
    alert('⚠️ Please select at least one notification method (Email or SMS)');
    return;
  }

  const confirmMsg = 'Are you sure you want to send a password reset link to this student?';
  if (!confirm(confirmMsg)) return;

  const resetData = {
    studentEmail: document.getElementById('editEmail')?.value || '',
    studentPhone: document.getElementById('editPhone')?.value || '',
    sendEmail,
    sendSms,
    resetToken: generateResetToken(),
    expiresIn: '24 hours'
  };

  console.log('Password Reset Request:', resetData);

  let notificationMsg = '';
  if (sendEmail && sendSms) notificationMsg = 'Password reset link sent via Email and SMS!';
  else if (sendEmail) notificationMsg = 'Password reset link sent via Email!';
  else notificationMsg = 'Password reset link sent via SMS!';

  alert(`✅ ${notificationMsg}\n\nThe link will expire in 24 hours.`);
}

function toggleEditPassword() {
  const passwordEl = document.getElementById('editNewPassword');
  if (!passwordEl) return;
  const toggleBtn = editStudentModal ? editStudentModal.querySelector('.password-toggle') : null;
  if (!toggleBtn) return;

  if (editPasswordVisible) {
    passwordEl.type = 'password';
    toggleBtn.textContent = '👁️';
    editPasswordVisible = false;
  } else {
    passwordEl.type = 'text';
    toggleBtn.textContent = '🙈';
    editPasswordVisible = true;
  }
}

function checkEditPasswordStrength() {
  const passwordEl = document.getElementById('editNewPassword');
  const strengthEl = document.getElementById('editPasswordStrength');
  const fillEl = document.getElementById('editStrengthFill');
  if (!passwordEl || !strengthEl || !fillEl) return;

  const password = passwordEl.value || '';
  if (!password.length) {
    strengthEl.className = 'password-strength';
    fillEl.style.width = '0%';
    return;
  }

  let strength = 0;
  if (password.length >= 8) strength++;
  if (password.length >= 12) strength++;
  if (/[a-z]/.test(password)) strength++;
  if (/[A-Z]/.test(password)) strength++;
  if (/[0-9]/.test(password)) strength++;
  if (/[^a-zA-Z0-9]/.test(password)) strength++;

  if (strength <= 2) {
    strengthEl.className = 'password-strength strength-weak';
  } else if (strength <= 4) {
    strengthEl.className = 'password-strength strength-medium';
  } else {
    strengthEl.className = 'password-strength strength-strong';
  }
}

function generateEditPassword() {
  const passwordEl = document.getElementById('editNewPassword');
  if (!passwordEl) return;

  const length = 12;
  const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
  let password = '';

  password += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[Math.floor(Math.random() * 26)];
  password += 'abcdefghijklmnopqrstuvwxyz'[Math.floor(Math.random() * 26)];
  password += '0123456789'[Math.floor(Math.random() * 10)];
  password += '!@#$%^&*'[Math.floor(Math.random() * 8)];

  for (let i = password.length; i < length; i++) {
    password += charset[Math.floor(Math.random() * charset.length)];
  }

  password = password.split('').sort(() => Math.random() - 0.5).join('');
  passwordEl.value = password;
  checkEditPasswordStrength();

  // Show password after generating (matches edit_student_form.html behavior)
  passwordEl.type = 'text';
  const toggleBtn = editStudentModal ? editStudentModal.querySelector('.password-toggle') : null;
  if (toggleBtn) toggleBtn.textContent = '🙈';
  editPasswordVisible = true;
}

function autoGenerateEditPassword() {
  generateEditPassword();
  alert('Strong password generated! The password is now visible in the field.');
}

async function sendEditNewPassword() {
  if (!editingRichStudentId) {
    alert('⚠️ Please open a student to edit first.');
    return;
  }

  const newPassword = document.getElementById('editNewPassword')?.value || '';
  const sendEmail = !!document.getElementById('editSendNewPwEmail')?.checked;
  const sendSms = !!document.getElementById('editSendNewPwSms')?.checked;

  if (!newPassword || !newPassword.trim()) {
    alert('⚠️ Please enter a new password or use the generate button');
    return;
  }

  if (newPassword.length < 6) {
    alert('⚠️ Password must be at least 6 characters long');
    return;
  }

  if (!sendEmail && !sendSms) {
    alert('⚠️ Please select at least one notification method (Email or SMS)');
    return;
  }

  const confirmMsg = 'Are you sure you want to create and send a new password to this student?\n\nThe student\'s current password will be replaced.';
  if (!confirm(confirmMsg)) return;

  const token = await ensureJWT();
  if (!token) {
    alert('Authentication required. Please login as admin and retry.');
    return;
  }

  const payload = { password: newPassword };

  const doPut = async (bearer) => {
    const res = await fetch(`${API_BASE}/api/v1/students/${editingRichStudentId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${bearer}`
      },
      credentials: 'include',
      body: JSON.stringify(payload)
    });
    const parsed = await parseJSONOrText(res);
    return { res, parsed };
  };

  const doFallbackPost = async (bearer) => {
    const res = await fetch(`${API_BASE}/api/v1/students/${editingRichStudentId}/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${bearer}`
      },
      credentials: 'include',
      body: JSON.stringify(payload)
    });
    const parsed = await parseJSONOrText(res);
    return { res, parsed };
  };

  let { res, parsed } = await doPut(token);

  if (res.status === 401 || res.status === 403) {
    localStorage.removeItem('admin_jwt_token');
    jwtToken = null;
    await fetchJWTToken();
    const refreshed = jwtToken;
    if (!refreshed) {
      alert('Unauthorized. Please re-login as admin.');
      return;
    }
    ({ res, parsed } = await doPut(refreshed));
  }

  if (!res.ok && (!parsed.json) && parsed.text && parsed.text.trim().startsWith('<')) {
    const bearer = jwtToken || localStorage.getItem('admin_jwt_token');
    if (bearer) {
      ({ res, parsed } = await doFallbackPost(bearer));
    }
  }

  if (!res.ok || !(parsed.json && parsed.json.success)) {
    const statusPart = `HTTP ${res.status}`;
    const apiError = (parsed.json && (parsed.json.error || parsed.json.message)) || null;
    const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
    const details = apiError || textSnippet || 'Unknown error';
    alert(`Failed to update password: ${statusPart} - ${details}`);
    return;
  }

  // Safe logging (mask password)
  const passwordData = {
    studentEmail: document.getElementById('editEmail')?.value || '',
    studentPhone: document.getElementById('editPhone')?.value || '',
    newPassword: '[PROTECTED]',
    sendEmail,
    sendSms,
    createdBy: 'Admin',
    createdAt: new Date().toISOString()
  };
  console.log('New Password Request:', passwordData);

  let notificationMsg = '';
  if (sendEmail && sendSms) notificationMsg = 'New password sent via Email and SMS!';
  else if (sendEmail) notificationMsg = 'New password sent via Email!';
  else notificationMsg = 'New password sent via SMS!';

  alert(`✅ ${notificationMsg}\n\nStudent can now login with the new password.`);

  // Clear after sending
  const newPwEl = document.getElementById('editNewPassword');
  if (newPwEl) newPwEl.value = '';
  const strengthEl = document.getElementById('editPasswordStrength');
  if (strengthEl) strengthEl.className = 'password-strength';
  const fillEl = document.getElementById('editStrengthFill');
  if (fillEl) fillEl.style.width = '0%';
}

async function submitAddStudentForm() {
  if (!addStudentFormEl || !addStudentSubmitBtn) return;

  courseModalContext = 'add';

  if (!addStudentFormEl.checkValidity()) {
    addStudentFormEl.reportValidity();
    return;
  }

  if (!addSelectedCourses.length) {
    alert('⚠️ Please add at least one course');
    return;
  }

  if (passwordInput && passwordInput.value.length < 6) {
    alert('⚠️ Password must be at least 6 characters long');
    return;
  }

  addStudentSubmitBtn.disabled = true;
  addStudentSubmitBtn.classList.add('loading');
  addStudentSubmitBtn.innerHTML = '<span class="spinner"></span> Adding Student...';

  const nameVal = document.getElementById('studentName')?.value || '';
  const emailVal = document.getElementById('email')?.value || '';
  const phoneVal = document.getElementById('phone')?.value || '';
  const classVal = document.getElementById('studentClass')?.value || '';
  const boardVal = document.getElementById('board')?.value || '';
  const passwordVal = passwordInput?.value || '';
  // Store only course names in DB (no class suffix).
  const coursesString = coursesArrayToDbString(addSelectedCourses, classVal);
  const today = new Date().toISOString().slice(0, 10);

  const payload = {
    name: nameVal,
    email: emailVal,
    courses: coursesString,
    date: today,
    // Map rich form fields to Student model columns
    mobile: phoneVal ? String(phoneVal).replace(/\D/g, '').slice(-10) : '',
    class: classVal,
    syllabus: boardVal,
    password: passwordVal,
    status: 'active'
  };

  try {
    const token = await ensureJWT();
    if (!token) {
      alert('Authentication required. Please login as admin and retry.');
      return;
    }

    const doCreate = async (bearer) => {
      const res = await fetch(`${API_BASE}/api/v1/students`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${bearer}`
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      const parsed = await parseJSONOrText(res);
      return { res, parsed };
    };

    let { res, parsed } = await doCreate(token);

    // If unauthorized/forbidden, refresh admin JWT once via /admin/api/get-jwt-token and retry
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem('admin_jwt_token');
      jwtToken = null;
      await fetchJWTToken();
      const refreshed = jwtToken;
      if (!refreshed) {
        alert('Unauthorized. Please re-login as admin.');
        return;
      }
      ({ res, parsed } = await doCreate(refreshed));
    }

    if (res.ok && parsed.json && parsed.json.success) {
      const newId = parsed.json.id;

      // If a profile photo was selected, upload it to /api/v1/students/<id>/avatar
      const fileInput = document.getElementById('profilePhoto');
      const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;

      if (newId && file) {
        try {
          const formData = new FormData();
          formData.append('avatar', file);

          const avatarRes = await fetch(`${API_BASE}/api/v1/students/${newId}/avatar`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${jwtToken || localStorage.getItem('admin_jwt_token') || token}`
            },
            credentials: 'include',
            body: formData
          });

          if (!avatarRes.ok) {
            console.warn('Avatar upload failed with status', avatarRes.status);
          }
        } catch (e) {
          console.error('Avatar upload failed:', e);
        }
      }

      if (addStudentSuccessMessage) {
        let notificationMsg = '';
        const sendEmail = document.getElementById('sendEmail');
        const sendSms = document.getElementById('sendSms');
        const emailChecked = !!(sendEmail && sendEmail.checked);
        const smsChecked = !!(sendSms && sendSms.checked);
        if (emailChecked && smsChecked) notificationMsg = ' Email and SMS notifications queued.';
        else if (emailChecked) notificationMsg = ' Email notification queued.';
        else if (smsChecked) notificationMsg = ' SMS notification queued.';
        addStudentSuccessMessage.textContent = `✓ Student added successfully!${notificationMsg}`;
        addStudentSuccessMessage.style.display = 'block';
      }
      showFeedback('Student added successfully', 'success');
      await fetchAndRenderStudents();
      setTimeout(() => {
        closeAddStudentModal();
      }, 1200);
      return;
    }

    const statusPart = `HTTP ${res.status}`;
    const apiError = (parsed.json && (parsed.json.error || parsed.json.message)) || null;
    const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
    const details = apiError || textSnippet || 'Unknown error';
    alert(`Failed to add: ${statusPart} - ${details}`);
  } catch (err) {
    console.error('Add via rich form failed:', err);
    alert('Failed to add student');
  } finally {
    addStudentSubmitBtn.disabled = false;
    addStudentSubmitBtn.classList.remove('loading');
    addStudentSubmitBtn.innerHTML = 'Add Student & Send Credentials';
  }
}

async function submitEditStudentForm() {
  if (!editStudentFormEl || !editStudentSaveBtn || !editingRichStudentId) return;

  courseModalContext = 'edit';

  if (!editStudentFormEl.checkValidity()) {
    editStudentFormEl.reportValidity();
    return;
  }

  if (!editSelectedCourses.length) {
    alert('⚠️ Please add at least one course');
    return;
  }

  editStudentSaveBtn.disabled = true;
  editStudentSaveBtn.classList.add('loading');
  editStudentSaveBtn.innerHTML = '<span class="spinner"></span> Saving Changes...';

  const nameVal = document.getElementById('editStudentName')?.value || '';
  const emailVal = document.getElementById('editEmail')?.value || '';
  const phoneVal = document.getElementById('editPhone')?.value || '';
  const classVal = document.getElementById('editStudentClass')?.value || '';
  const boardVal = document.getElementById('editBoard')?.value || '';
  const statusVal = document.getElementById('editStatus')?.value || 'active';
  const enrollmentDateVal = document.getElementById('editEnrollmentDate')?.value || '';

  const editNewPasswordVal = document.getElementById('editNewPassword')?.value || '';
  const shouldUpdatePassword = !!(editNewPasswordVal && editNewPasswordVal.trim().length);
  if (shouldUpdatePassword && editNewPasswordVal.length < 6) {
    alert('⚠️ Password must be at least 6 characters long');
    return;
  }

  if (shouldUpdatePassword) {
    const confirmMsg = 'You entered a new password. Save Changes will update the student\'s password too. Continue?';
    if (!confirm(confirmMsg)) {
      return;
    }
  }

  // Store only course names in DB (no class suffix).
  const coursesString = coursesArrayToDbString(editSelectedCourses, classVal);

  const payload = {
    name: nameVal,
    email: emailVal,
    courses: coursesString,
    date: enrollmentDateVal,
    mobile: phoneVal ? String(phoneVal).replace(/\D/g, '').slice(-10) : '',
    class: classVal,
    syllabus: boardVal,
    status: (String(statusVal).toLowerCase() === 'inactive') ? 'inactive' : 'active'
  };

  if (shouldUpdatePassword) {
    payload.password = editNewPasswordVal;
  }

  try {
    const token = await ensureJWT();
    if (!token) {
      alert('Authentication required. Please login as admin and retry.');
      return;
    }

    const doPut = async (bearer) => {
      const res = await fetch(`${API_BASE}/api/v1/students/${editingRichStudentId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${bearer}`
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      const parsed = await parseJSONOrText(res);
      return { res, parsed };
    };

    const doFallbackPost = async (bearer) => {
      const res = await fetch(`${API_BASE}/api/v1/students/${editingRichStudentId}/update`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${bearer}`
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      const parsed = await parseJSONOrText(res);
      return { res, parsed };
    };

    let { res, parsed } = await doPut(token);

    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem('admin_jwt_token');
      jwtToken = null;
      await fetchJWTToken();
      const refreshed = jwtToken;
      if (!refreshed) {
        alert('Unauthorized. Please re-login as admin.');
        return;
      }
      ({ res, parsed } = await doPut(refreshed));
    }

    // Some cloud environments block PUT; detect HTML errors and retry via POST fallback
    if (!res.ok && (!parsed.json) && parsed.text && parsed.text.trim().startsWith('<')) {
      const bearer = jwtToken || localStorage.getItem('admin_jwt_token');
      if (bearer) {
        ({ res, parsed } = await doFallbackPost(bearer));
      }
    }

    if (res.ok && parsed.json && parsed.json.success) {
      // Optional avatar upload
      const fileInput = document.getElementById('editProfilePhoto');
      const file = fileInput && fileInput.files && fileInput.files[0];
      if (file) {
        const bearer = jwtToken || localStorage.getItem('admin_jwt_token');
        if (bearer) {
          const fd = new FormData();
          fd.append('avatar', file);
          try {
            await fetch(`${API_BASE}/api/v1/students/${editingRichStudentId}/avatar`, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${bearer}` },
              credentials: 'include',
              body: fd
            });
          } catch (e) {
            console.warn('Avatar upload failed after edit; continuing.', e);
          }
        }
      }

      if (editStudentSuccessMessage) {
        editStudentSuccessMessage.textContent = '✓ Student updated successfully!';
        editStudentSuccessMessage.style.display = 'block';
      }

      showFeedback('Student updated successfully', 'success');

      // Clear password field after successful save (avoid leaving it visible in DOM)
      if (shouldUpdatePassword) {
        const pwEl = document.getElementById('editNewPassword');
        if (pwEl) {
          pwEl.value = '';
          pwEl.type = 'password';
        }
        const strengthEl = document.getElementById('editPasswordStrength');
        if (strengthEl) strengthEl.className = 'password-strength';
        const fillEl = document.getElementById('editStrengthFill');
        if (fillEl) fillEl.style.width = '0%';
        editPasswordVisible = false;
        const toggleBtn = editStudentModal ? editStudentModal.querySelector('.password-toggle') : null;
        if (toggleBtn) toggleBtn.textContent = '👁️';
      }

      await fetchAndRenderStudents();
      setTimeout(() => closeEditStudentModal(), 1400);
      return;
    }

    const statusPart = `HTTP ${res.status}`;
    const apiError = (parsed.json && (parsed.json.error || parsed.json.message)) || null;
    const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
    const details = apiError || textSnippet || 'Unknown error';
    alert(`Failed to update: ${statusPart} - ${details}`);
  } catch (err) {
    console.error('Edit failed:', err);
    alert('Failed to update student');
  } finally {
    editStudentSaveBtn.disabled = false;
    editStudentSaveBtn.classList.remove('loading');
    editStudentSaveBtn.textContent = 'Save Changes';
  }
}

function handleModalSave(e) {
  e.preventDefault();
  
  const payload = {
    name: modalName.value || '',
    email: modalEmail.value || '',
    mobile: modalMobile.value || '',
    date: modalEnrollment.value || '',
    courses: modalCourses.value || '',
    status: modalStatus.value || 'active'
  };
  
  if (editingStudentId === null) {
    // Add new student
    ensureJWT().then((token) => {
      if (!token) { alert('Authentication required. Please login as admin and retry.'); return; }
    fetch(`${API_BASE}/api/v1/students`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      credentials: 'include',
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          closeModal();
          fetchAndRenderStudents(); // Refresh from DB
          showFeedback('Student added successfully', 'success');
        } else {
          alert('Failed to add: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(err => {
        console.error('Add failed:', err);
        alert('Failed to add student');
      });
    });
  } else {
    // Update existing student
    (async () => {
      const token = await ensureJWT();
      if (!token) { alert('Authentication required. Please login as admin and retry.'); return; }
      const s = findStudent(editingStudentId);
      if (!s) return closeModal();

      const doPut = async (bearer) => {
        const res = await fetch(`${API_BASE}/api/v1/students/${editingStudentId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${bearer}`
          },
          credentials: 'include',
          body: JSON.stringify(payload)
        });
        const parsed = await parseJSONOrText(res);
        return { res, parsed };
      };

      const doFallbackPost = async (bearer) => {
        const res = await fetch(`${API_BASE}/api/v1/students/${editingStudentId}/update`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${bearer}`
          },
          credentials: 'include',
          body: JSON.stringify(payload)
        });
        const parsed = await parseJSONOrText(res);
        return { res, parsed };
      };

      try {
        let { res, parsed } = await doPut(token);

        if (res.status === 401 || res.status === 403) {
          localStorage.removeItem('admin_jwt_token');
          jwtToken = null;
          await fetchJWTToken();
          const refreshed = jwtToken;
          if (!refreshed) { alert('Unauthorized. Please re-login as admin.'); return; }
          ({ res, parsed } = await doPut(refreshed));
        }

        // If still 403 with HTML body (proxy page), try POST fallback
        if (res.status === 403 && (!parsed.json) && parsed.text && parsed.text.trim().startsWith('<')) {
          console.warn('PUT blocked upstream (HTML 403). Retrying via POST /update fallback...');
          const bearer = jwtToken || localStorage.getItem('admin_jwt_token');
          if (!bearer) { alert('Unauthorized. Please re-login as admin.'); return; }
          ({ res, parsed } = await doFallbackPost(bearer));
        }

        if (res.ok && parsed.json && parsed.json.success) {
          s.name = payload.name;
          s.email = payload.email;
          s.mobile = payload.mobile;
          s.enrollmentDate = payload.date;
          s.courses = payload.courses;
          s.status = payload.status;
          closeModal();
          applyFilters();
          updateStats(studentsData);
          showFeedback('Student updated successfully', 'success');
          return;
        }

        const statusPart = `HTTP ${res.status}`;
        const apiError = (parsed.json && (parsed.json.error || parsed.json.message)) || null;
        const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
        const details = apiError || textSnippet || 'Unknown error';
        if (parsed.text && parsed.text.trim().startsWith('<')) {
          console.warn('Non-JSON error response body (truncated):', parsed.text.substring(0, 1000));
        }
        alert(`Failed to update: ${statusPart} - ${details}`);
      } catch (err) {
        console.error('Update failed:', err);
        alert('Failed to update student');
      }
    })();
  }
}
window.viewStudent = viewStudent;
window.editStudent = editStudent;
window.messageStudent = messageStudent;
window.removeStudent = removeStudent;
// Expose helpers used by inline handlers in the Add Student form
window.openCourseModal = openCourseModal;
window.closeCourseModal = closeCourseModal;
window.addCourse = addCourse;
window.removeCourse = removeCourse;
window.validateAndPreviewPhoto = validateAndPreviewPhoto;
window.openAddModal = openAddModal;
window.loadCourses = loadCourses;
window.togglePassword = togglePassword;
window.generatePassword = generatePassword;
window.autoGeneratePassword = autoGeneratePassword;
window.checkPasswordStrength = checkPasswordStrength;

// Expose helpers used by inline handlers in the Edit Student password section
window.sendEditPasswordReset = sendEditPasswordReset;
window.toggleEditPassword = toggleEditPassword;
window.generateEditPassword = generateEditPassword;
window.autoGenerateEditPassword = autoGenerateEditPassword;
window.checkEditPasswordStrength = checkEditPasswordStrength;
window.sendEditNewPassword = sendEditNewPassword;

function formatDate(dateString) {
  if (!dateString) return '';
  // Handle YYYY-MM-DD format from database
  if (typeof dateString === 'string' && dateString.includes('-')) {
    const [year, month, day] = dateString.split('-');
    const d = new Date(year, parseInt(month) - 1, day);
    return d.toLocaleDateString('en-US', { year:'numeric', month:'short', day:'numeric' });
  }
  const d = new Date(dateString);
  return d.toLocaleDateString('en-US', { year:'numeric', month:'short', day:'numeric' });
}

function parseDateStrict(dateString) {
  if (!dateString) return null;
  if (typeof dateString === 'string' && dateString.includes('-')) {
    const [year, month, day] = dateString.split('-');
    const y = parseInt(year, 10), m = parseInt(month, 10), d = parseInt(day, 10);
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;
    const dt = new Date(y, m - 1, d);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }
  const dt = new Date(dateString);
  return Number.isNaN(dt.getTime()) ? null : dt;
}
