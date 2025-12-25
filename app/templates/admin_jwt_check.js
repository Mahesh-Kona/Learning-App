// Utility to decode JWT and check admin role
function isAdminToken(token) {
  if (!token) return false;
  try {
    const payload = token.split('.')[1];
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return decoded.role === 'admin';
  } catch {
    return false;
  }
}

// Try to obtain an admin JWT using existing admin session
async function getAdminToken() {
  let token = localStorage.getItem('admin_jwt_token') || localStorage.getItem('access_token');
  if (isAdminToken(token)) {
    return token;
  }

  try {
    const res = await fetch('/admin/api/get-jwt-token', { credentials: 'include' });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    if (!data || !data.success || !data.access_token) return null;
    token = data.access_token;
    // Cache for subsequent calls
    localStorage.setItem('admin_jwt_token', token);
    localStorage.setItem('access_token', token);
    return token;
  } catch {
    return null;
  }
}

// Patch deleteCard to ensure an admin token before sending request
window.deleteCard = async function(id) {
  if (!confirm('Are you sure you want to delete this card?')) return;

  let token = await getAdminToken();
  if (!token || !isAdminToken(token)) {
    alert('You are not logged in as admin. Please log in as admin to delete cards.');
    return;
  }

  let res;
  try {
    const doDelete = async (tkn) => fetch(`/api/v1/cards/${id}`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': 'Bearer ' + tkn }
    });

    res = await doDelete(token);
    if (res.status === 401 || res.status === 422) {
      const newToken = await refreshAccessToken();
      if (newToken && isAdminToken(newToken)) {
        token = newToken;
        localStorage.setItem('admin_jwt_token', token);
        res = await doDelete(token);
      }
    }

    if (!res.ok) throw new Error('Failed to delete card');
    if (typeof cards !== 'undefined' && typeof render === 'function') {
      cards = cards.filter(c => c.id !== id);
      render();
    }
  } catch (e) {
    let msg = 'Error deleting card: ' + (e.message || e);
    if (res) {
      try {
        const err = await res.json();
        if (err && err.error) msg += '\n' + err.error;
      } catch {}
    }
    alert(msg);
  }
};
