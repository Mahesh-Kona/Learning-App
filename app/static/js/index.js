document.addEventListener('DOMContentLoaded', () => {
  const roles = document.querySelectorAll('.role-option');
  const form = document.getElementById('loginForm');
  const roleInput = document.getElementById('roleInput');

  // Role selection logic
  roles.forEach(role => {
    role.addEventListener('click', () => {
      roles.forEach(r => r.classList.remove('selected'));
      role.classList.add('selected');
      // update hidden role input immediately
      if (roleInput) {
        roleInput.value = role.dataset.role;
      }
    });
  });
  // Form submission: send via fetch with X-Requested-With so server returns JSON and we can show inline errors
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const selectedRole = document.querySelector('.role-option.selected');
    if (!selectedRole) {
      showAlert('Please select your role (Teacher or Admin).');
      return;
    }

    if (selectedRole.dataset.role !== 'admin') {
      showAlert('Please select Admin to access the admin dashboard.');
      return;
    }

  // prepare form data
  const formData = new URLSearchParams();
  formData.append('email', document.getElementById('email').value);
  formData.append('password', document.getElementById('password').value);
  formData.append('role', roleInput ? roleInput.value : selectedRole.dataset.role);
  // include remember checkbox state (1 for checked)
  const rememberEl = document.getElementById('remember');
  formData.append('remember', rememberEl && rememberEl.checked ? '1' : '0');

    try {
      const resp = await fetch(form.action, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData.toString(),
        credentials: 'same-origin'
      });

      const json = await resp.json().catch(() => null);
      if (json && json.success) {
        // Store tokens in localStorage for admin checks and API calls
        if (json.access_token) {
          localStorage.setItem('access_token', json.access_token);
        }
        if (json.refresh_token) {
          localStorage.setItem('refresh_token', json.refresh_token);
        }
        // redirect to server-specified URL or default dashboard
        window.location.href = json.redirect || '/admin/dashboard';
        return;
      }

      // show error from server or a generic message
      const msg = (json && (json.error || json.message)) || 'Login failed — please check your credentials and try again.';
      showAlert(msg);
    } catch (err) {
      showAlert('Network error while attempting login. Please try again.');
      console.error('Login fetch error', err);
    }
  });

  // Alert helpers
  const alertBox = document.getElementById('loginAlert');
  const alertMsg = document.getElementById('loginAlertMsg');
  const alertClose = document.getElementById('loginAlertClose');

  function showAlert(message) {
    if (!alertBox || !alertMsg) return alert(message);
    alertMsg.textContent = message;
    alertBox.style.display = 'flex';
  }

  if (alertClose && alertBox) {
    alertClose.addEventListener('click', () => {
      alertBox.style.display = 'none';
    });
  }
});
