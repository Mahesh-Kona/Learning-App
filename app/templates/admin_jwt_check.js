function decodeJwtPayload(token) {
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}

function isTokenExpired(token, leewaySeconds = 30) {
  const decoded = decodeJwtPayload(token);
  if (!decoded || !decoded.exp) return false;
  const now = Math.floor(Date.now() / 1000);
  return now >= (Number(decoded.exp) - Number(leewaySeconds));
}

// Utility to decode JWT and check admin role
function isAdminToken(token) {
  const decoded = decodeJwtPayload(token);
  return !!decoded && decoded.role === 'admin';
}

// Refresh access token using refresh token (stored in localStorage)
async function refreshAccessToken() {
  const refresh = localStorage.getItem('refresh_token');
  if (!refresh) return null;

  try {
    const res = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': 'Bearer ' + refresh
      }
    });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    if (!data || !data.success || !data.access_token) return null;
    localStorage.setItem('access_token', data.access_token);
    return data.access_token;
  } catch {
    return null;
  }
}

window.refreshAccessToken = refreshAccessToken;

// Try to obtain an admin JWT using existing admin session
async function getAdminToken() {
  let token = localStorage.getItem('admin_jwt_token') || localStorage.getItem('access_token');
  if (isAdminToken(token) && !isTokenExpired(token)) {
    return token;
  }

  if (isAdminToken(token) && isTokenExpired(token)) {
    const refreshed = await refreshAccessToken();
    if (refreshed && isAdminToken(refreshed) && !isTokenExpired(refreshed)) {
      localStorage.setItem('admin_jwt_token', refreshed);
      localStorage.setItem('access_token', refreshed);
      return refreshed;
    }
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
    const doDelete = async (tkn) => fetch(`/api/v1/cards/${id}/delete`, {
      method: 'POST',
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
