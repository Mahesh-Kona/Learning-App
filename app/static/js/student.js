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
let editingStudentId = null;

// Fetch and store JWT token for API calls
let jwtToken = null;

document.addEventListener('DOMContentLoaded', () => {
  // Fetch JWT token first, then load data
  fetchJWTToken().then(() => {
    fetchAndRenderStudents();
    fetchAndRenderLeaderboard();
    attachEventListeners();
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
  tr.innerHTML = `
    <td><input type="checkbox" class="student-checkbox" data-id="${student.id}" onchange="handleCheckbox('${student.id}')"></td>
    <td>${student.id}</td>
    <td><strong>${student.name}</strong></td>
    <td>${studentEmail}</td>
    <td>${formatDate(student.enrollmentDate)}</td>
    <td>${student.courses || ''}</td>
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
  const s = findStudent(id);
  if (!s) return alert('Student not found');
  openEditModal(s);
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
  editingStudentId = null;
  modalTitle.textContent = 'Add New Student';
  modalName.value = '';
  modalEmail.value = '';
  modalMobile.value = '';
  modalEnrollment.value = '';
  modalCourses.value = '';
  modalStatus.value = 'active';
  studentModal.classList.remove('hidden');
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
          alert('Student added successfully');
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
          alert('Student updated successfully');
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
