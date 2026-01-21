// EduSaint Dashboard Script
document.addEventListener('DOMContentLoaded', function () {
  // Notification click
  const notification = document.querySelector('.notification');
  if (notification) {
    notification.addEventListener('click', function () {
      // Navigate to admin notifications page
      window.location.href = '/admin/notifications';
    });
  }

  // Quick action buttons
  document.querySelectorAll('.action-btn').forEach((btn) => {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      const action = this.querySelector('span').textContent.trim();

      const actionLower = action.toLowerCase();

      // Redirect specific quick actions to their proper pages
      if (actionLower.includes('create course')) {
        window.location.href = '/admin/create_course';
      } else if (actionLower.includes('add student')) {
        // Use the anchor's href so query params like ?open_add=1 work
        const href = this.getAttribute('href');
        if (href) {
          window.location.href = href;
        }
      } else {
        alert(`Opening ${action} form...`);
      }
    });
  });

  // User profile click
  const userProfile = document.querySelector('.user-profile');
  if (userProfile) {
    userProfile.addEventListener('click', function () {
      alert('Opening profile settings...');
    });
  }

  // View button
  document.querySelectorAll('.view-btn').forEach((button) => {
    button.addEventListener('click', () => alert('Opening student details...'));
  });
});