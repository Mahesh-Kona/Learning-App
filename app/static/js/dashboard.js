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

      // ✅ Redirect if the action is "Create Course" to the Flask route
      if (action.toLowerCase().includes('create course')) {
        window.location.href = '/admin/create_course';
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