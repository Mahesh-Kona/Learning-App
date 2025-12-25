document.addEventListener('DOMContentLoaded', function () {
    // Helper to get JWT token from localStorage (adjust key if needed)
    function getJWT() {
      return localStorage.getItem('admin_jwt_token');
    }

    // Debug: Show current user/role if available
    fetch('/admin/whoami').then(async res => {
      if (res.ok) {
        const data = await res.json();
        if (data && data.user) {
          const info = document.createElement('div');
          info.style = 'font-size:13px;color:#888;margin-bottom:8px;';
          info.textContent = `Logged in as: ${data.user} (${data.role || 'unknown role'})`;
          document.querySelector('.dashboard')?.prepend(info);
        }
      }
    }).catch(()=>{});
  const form = document.getElementById('notificationForm');
  const tableBody = document.getElementById('historyTable');
  const statusBox = document.getElementById('status');

  async function refreshHistory() {
    try {
      // Using external notifications service schema
      const res = await fetch('/admin/notifications/api');
      const rows = await res.json();
      renderTable(Array.isArray(rows) ? rows : []);
    } catch (e) {
      console.warn('Failed to load notifications', e);
    }
  }

  function formatDate(ts) {
    if (!ts) return '';
    // Expect ISO like 2025-12-19T23:30:29 → 2025-12-19 23:30
    try {
      const s = String(ts);
      if (s.includes('T')) {
        const [d, t] = s.split('T');
        return `${d} ${t.slice(0,5)}`;
      }
      // fallback: try Date
      const d = new Date(ts);
      const pad = (n)=>String(n).padStart(2,'0');
      return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return ts;
    }
  }

  function splitDateTime(ts) {
    if (!ts) return { date: '', time: '' };
    try {
      const s = String(ts);
      if (s.includes('T')) {
        const [d, t] = s.split('T');
        return { date: d, time: t.slice(0,5) };
      }
      const d = new Date(ts);
      const pad = (n)=>String(n).padStart(2,'0');
      return {
        date: `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`,
        time: `${pad(d.getHours())}:${pad(d.getMinutes())}`
      };
    } catch {
      return { date: '', time: '' };
    }
  }

  let editId = null;

  form?.addEventListener('submit', async function (e) {
    e.preventDefault();
    const title = document.getElementById('titleInput').value.trim();
    const message = document.getElementById('messageInput').value.trim();
    const category = document.getElementById('categoryInput').value;
    const target = document.getElementById('targetInput').value.trim();
    const date = document.getElementById('dateInput').value;
    const time = document.getElementById('timeInput').value;

    if (!title || !message) {
      statusBox.textContent = 'Title and message are required';
      statusBox.style.color = 'red';
      return;
    }

    // Client-side validation: if scheduling, only accept future times
    if (date && time) {
      try {
        const scheduled = new Date(`${date}T${time}:00`);
        const now = new Date();
        if (isNaN(scheduled.getTime())) {
          statusBox.textContent = 'Invalid date/time';
          statusBox.style.color = 'red';
          return;
        }
        if (scheduled <= now) {
          statusBox.textContent = 'Schedule must be in the future';
          statusBox.style.color = 'red';
          return;
        }
      } catch (err) {
        statusBox.textContent = 'Invalid date/time';
        statusBox.style.color = 'red';
        return;
      }
    }

    const payload = { title, message, category, target, date, time };
    try {
      let res;
      const jwt = getJWT();
      if (editId) {
        res = await fetch(`/admin/notifications/api/${editId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(jwt ? { 'Authorization': 'Bearer ' + jwt } : {})
          },
          body: JSON.stringify(payload)
        });
      } else {
        res = await fetch('/admin/notifications/api', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(jwt ? { 'Authorization': 'Bearer ' + jwt } : {})
          },
          body: JSON.stringify(payload)
        });
      }
      if (res.status === 401) {
        statusBox.textContent = 'Not authenticated. Please log in as admin.';
        statusBox.style.color = 'red';
        return;
      }
      // Removed 403 Forbidden error message
      const data = await res.json();
      if (data && data.success) {
        statusBox.textContent = editId ? 'Notification updated' : 'Notification queued successfully';
        statusBox.style.color = 'green';
        form.reset();
        editId = null;
        refreshHistory();
      } else {
        statusBox.textContent = (data && data.error) || 'Failed to send';
        statusBox.style.color = 'red';
      }
    } catch (err) {
      statusBox.textContent = 'Error sending notification';
      statusBox.style.color = 'red';
    }
  });

  function renderTable(items) {
    tableBody.innerHTML = '';
    (items || []).forEach((n) => {
      const row = document.createElement('tr');
      const isScheduled = String(n.status || '').toLowerCase() === 'scheduled';
      const dateShown = formatDate(isScheduled ? n.scheduled_at : (n.created_at || n.scheduled_at));
      row.innerHTML = `
        <td>${n.title || ''}</td>
        <td>${n.category || ''}</td>
        <td>${n.target || ''}</td>
        <td><span class="badge ${isScheduled ? 'scheduled' : 'sent'}">${n.status || ''}</span></td>
        <td>${dateShown}</td>
        <td>
          <div class="actions">
           
            <a href="#" class="action delete" data-id="${n.id}">Delete</a>
          </div>
        </td>
      `;
      tableBody.appendChild(row);
    });
  }
//  <a href="#" class="action edit" data-id="${n.id}">Edit</a>
  tableBody.addEventListener('click', async (e) => {
    const btn = e.target.closest('a');
    if (!btn) return;
    e.preventDefault();
    const id = btn.getAttribute('data-id');
    if (btn.classList.contains('delete')) {
      if (!confirm('Delete this notification?')) return;
      try {
        const jwt = getJWT();

        const parseJSONOrText = async (res) => {
          const contentType = res.headers.get('content-type') || '';
          if (contentType.includes('application/json')) {
            try {
              const json = await res.json();
              return { json, text: null };
            } catch (e) {
              return { json: null, text: null };
            }
          }
          try {
            const text = await res.text();
            return { json: null, text };
          } catch (e) {
            return { json: null, text: null };
          }
        };

        const doDelete = async () => {
          const res = await fetch(`/admin/notifications/api/${id}`, {
            method: 'DELETE',
            headers: jwt ? { 'Authorization': 'Bearer ' + jwt } : {}
          });
          const parsed = await parseJSONOrText(res);
          return { res, parsed };
        };

        const doFallbackDeletePost = async () => {
          const res = await fetch(`/admin/notifications/api/${id}/delete`, {
            method: 'POST',
            headers: jwt ? { 'Authorization': 'Bearer ' + jwt } : {}
          });
          const parsed = await parseJSONOrText(res);
          return { res, parsed };
        };

        let { res, parsed } = await doDelete();

        if (res.status === 401) {
          statusBox.textContent = 'Not authenticated. Please log in as admin.';
          statusBox.style.color = 'red';
          return;
        }

        // If DELETE is blocked upstream (HTML 403 page), retry via POST fallback
        if (res.status === 403 && (!parsed.json) && parsed.text && parsed.text.trim().startsWith('<')) {
          console.warn('DELETE /admin/notifications/api blocked upstream (HTML 403). Retrying via POST fallback...');
          ({ res, parsed } = await doFallbackDeletePost());
        }

        if (res.ok) {
          const ok = parsed.json ? parsed.json.success : true;
          if (ok) {
            statusBox.textContent = 'Notification deleted successfully';
            statusBox.style.color = 'green';
            refreshHistory();
            return;
          }
        }

        const apiError = parsed.json && (parsed.json.error || parsed.json.message);
        const textSnippet = parsed.text ? parsed.text.substring(0, 200) : null;
        const details = apiError || textSnippet || 'Failed to delete notification';
        console.warn('Failed to delete notification:', res.status, details);
        statusBox.textContent = `Failed to delete notification (${res.status}).`;
        statusBox.style.color = 'red';
      } catch (err) {
        console.error('Error deleting notification', err);
        statusBox.textContent = 'Error deleting notification';
        statusBox.style.color = 'red';
      }
    }
    if (btn.classList.contains('edit')) {
      // Fetch full record to prefill all fields including message
      try {
        const res = await fetch(`/admin/notifications/api/${id}`);
        if (res.status === 401) {
          statusBox.textContent = 'Not authenticated. Please log in as admin.';
          statusBox.style.color = 'red';
          return;
        }
        // Removed 403 Forbidden error message
        const data = await res.json();
        if (data && data.success && data.notification) {
          const n = data.notification;
          document.getElementById('titleInput').value = n.title || '';
          document.getElementById('messageInput').value = n.message || '';
          document.getElementById('categoryInput').value = n.category || '';
          document.getElementById('targetInput').value = n.target || '';
          // Prefill date/time for scheduled notifications
          const isScheduled = String(n.status || '').toLowerCase() === 'scheduled';
          const dt = isScheduled ? splitDateTime(n.scheduled_at) : { date: '', time: '' };
          document.getElementById('dateInput').value = dt.date;
          document.getElementById('timeInput').value = dt.time;
          editId = id;
          statusBox.textContent = 'Editing notification…';
          statusBox.style.color = '#6b7280';
        }
      } catch (err) {
        console.warn('Failed to load notification for edit', err);
      }
    }
  });

  refreshHistory();
});
