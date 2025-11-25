// create_course.js copied to static
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('courseForm');
  const title = document.getElementById('courseTitle');
  const desc = document.getElementById('courseDescription');
  const category = document.getElementById('courseCategory');
  const cls = document.getElementById('courseClass');
  const price = document.getElementById('coursePrice');
  const thumbnail = document.getElementById('thumbnail');
  const resetBtn = document.getElementById('resetBtn');

  const previewImage = document.getElementById('previewImage');
  const previewTitle = document.getElementById('previewTitle');
  const previewDesc = document.getElementById('previewDesc');
  const previewCategory = document.getElementById('previewCategory');
  const previewClass = document.getElementById('previewClass');
  const openLessonBtn = document.getElementById('openLessonBtn');

  // Pricing options: toggle Paid vs Free course
  const pricingOptions = document.querySelectorAll('.pricing-option');
  const coursePriceGroup = document.getElementById('coursePrice') ? document.getElementById('coursePrice').closest('.form-group') : null;
  function setPricingSelection(value) {
    pricingOptions.forEach(opt => {
      if (opt.dataset && opt.dataset.value === value) opt.classList.add('selected'); else opt.classList.remove('selected');
    });
    if (value === 'free') {
      // hide/disable price input
      if (coursePriceGroup) coursePriceGroup.style.display = 'none';
      try { if (document.getElementById('coursePrice')) { document.getElementById('coursePrice').value = ''; document.getElementById('coursePrice').disabled = true; } } catch (e) {}
    } else {
      if (coursePriceGroup) coursePriceGroup.style.display = '';
      try { if (document.getElementById('coursePrice')) { document.getElementById('coursePrice').disabled = false; } } catch (e) {}
    }
  }
  pricingOptions.forEach(opt => {
    opt.addEventListener('click', (e) => {
      const v = opt.dataset && opt.dataset.value ? opt.dataset.value : 'paid';
      setPricingSelection(v);
    });
  });
  // initialize pricing UI based on current selected class (if any)
  const initial = document.querySelector('.pricing-option.selected');
  if (initial && initial.dataset && initial.dataset.value) {
    setPricingSelection(initial.dataset.value);
  }

  // Live preview updates
  title.addEventListener('input', () => previewTitle.textContent = title.value || 'Course Title');
  desc.addEventListener('input', () => previewDesc.textContent = desc.value || 'Course description will appear here.');
  category.addEventListener('change', () => previewCategory.textContent = 'Category: ' + (category.value || '-'));
  cls.addEventListener('change', () => previewClass.textContent = 'Class: ' + (cls.value || '-'));

  thumbnail.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => previewImage.src = reader.result;
    reader.readAsDataURL(file);
  });

  // Reset form
  resetBtn.addEventListener('click', () => {
    form.reset();
    // Clear the hidden file input explicitly (some browsers keep the file input value after form.reset())
    if (thumbnail) {
      try { thumbnail.value = ''; } catch (e) { /* ignore */ }
    }
    previewImage.src = 'https://via.placeholder.com/320x180.png?text=Thumbnail';
    previewTitle.textContent = 'Course Title';
    previewDesc.textContent = 'Course description will appear here.';
    previewCategory.textContent = 'Category: -';
    previewClass.textContent = 'Class: -';
    // Remove saved preview from localStorage so reset is persistent across reloads
    try { localStorage.removeItem('lastCourse'); } catch (e) { /* ignore */ }
  });

  // On submit: basic validation, then create asset (if file) and create course
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!title.value.trim() || !category.value || !cls.value) {
      alert('Please fill required fields: Course Title, Category, and Class.');
      return;
    }

    // Save a local copy for editor convenience
    const courseData = {
      title: title.value.trim(),
      description: desc.value.trim(),
      category: category.value,
      class: cls.value,
      price: price.value || null,
      thumbnail: previewImage.src
    };
    try { localStorage.setItem('lastCourse', JSON.stringify(courseData)); } catch (e) { /* ignore */ }

    // Build FormData for the final course POST (include all fields so both JS and non-JS flows match)
    const formData = new FormData();
    formData.append('title', title.value.trim());
    formData.append('description', desc.value.trim());
    formData.append('category', category.value);
    formData.append('class', cls.value);
    if (price.value) formData.append('price', price.value);
  // metadata fields
  const durationEl = document.getElementById('courseDuration');
  const weeklyEl = document.getElementById('weeklyHours');
  // syllabus and learning objectives (ensure they're included in FormData)
  const syllabusEl = document.getElementById('courseSyllabus');
  const objectivesEl = document.getElementById('learningObjectives');
    if (durationEl && durationEl.value) formData.append('duration', durationEl.value);
    if (weeklyEl && weeklyEl.value) formData.append('weekly_hours', weeklyEl.value);
    // difficulty radio
    const diff = document.querySelector('input[name="difficulty"]:checked');
    if (diff && diff.value) formData.append('difficulty', diff.value);
    // course type (video/live/hybrid/self-paced)
    try {
      const ctype = document.querySelector('input[name="course_type"]:checked');
      if (ctype && ctype.value) formData.append('course_type', ctype.value);
    } catch (e) { /* ignore */ }
    // include syllabus/objectives when present
    if (syllabusEl && syllabusEl.value) formData.append('syllabus', syllabusEl.value);
    if (objectivesEl && objectivesEl.value) formData.append('learning_objectives', objectivesEl.value);
    // stream
    const streamEl = document.getElementById('courseStream');
    if (streamEl && streamEl.value) formData.append('stream', streamEl.value);
    // tags: try tags-input value or existing .tag elements
    try {
      const tagsInput = document.querySelector('.tags-input');
      let tagsVal = '';
      if (tagsInput && tagsInput.value) {
        tagsVal = tagsInput.value;
      } else {
        const tagEls = document.querySelectorAll('.tags-input-container .tag');
        tagsVal = Array.from(tagEls).map(t => t.textContent.replace('\u00D7','').trim()).filter(Boolean).join(',');
      }
      if (tagsVal) formData.append('tags', tagsVal);
    } catch (e) { /* ignore */ }
    // publish / featured checkboxes
    try {
      const pub = document.getElementById('coursePublished');
      const feat = document.getElementById('featuredCourse');
      if (pub && pub.checked) formData.append('published', 'on');
      if (feat && feat.checked) formData.append('featured', 'on');
    } catch (e) { /* ignore */ }

    const file = thumbnail.files && thumbnail.files[0];

    try {
      // If user selected a file, upload it first to the central uploads API so it creates an Asset row
    if (file) {
        const uploadForm = new FormData();
        uploadForm.append('file', file);
        const upResp = await fetch('/api/v1/uploads', {
          method: 'POST',
          body: uploadForm,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const upJson = await upResp.json().catch(() => ({}));
        if (!upJson || !upJson.success) {
          console.error('Upload failed', upJson);
          alert('Image upload failed. Check console for details.');
          return;
        }
        // attach returned asset id and url to the course form data
        if (upJson.asset_id) formData.append('thumbnail_asset_id', upJson.asset_id);
        if (upJson.url) formData.append('thumbnail_url', upJson.url);
      } else if (previewImage && previewImage.src) {
        // no file selected; include preview data url (optional)
        formData.append('thumbnail_data_url', previewImage.src);
      }

      // Now create the course record
      const resp = await fetch('/admin/create_course', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const data = await resp.json().catch(() => ({}));
      console.log('Create course response', data);
      if (data && data.success && data.id) {
        // clear stored preview and reset the form so the thumbnail doesn't reappear
        try { localStorage.removeItem('lastCourse'); } catch (e) { /* ignore */ }
        try {
          form.reset();
          if (thumbnail) { try { thumbnail.value = ''; } catch (e) {} }
          previewImage.src = 'https://via.placeholder.com/320x180.png?text=Thumbnail';
        } catch (e) { /* ignore */ }
        // navigate to the lesson page for the created course
        window.location.href = '/admin/lesson' + `?course_id=${data.id}`;
      } else {
        alert('Course saved locally but failed to persist to server. Check console or try again.');
      }
    } catch (err) {
      console.error('Failed to create course', err);
      alert('Failed to create course on server. Check console for details.');
    }
  });

  // Intentionally do not auto-restore draft data from localStorage on page load.
  // This ensures the course image preview is empty when opening the create page
  // (e.g. after login). If you want a "Restore draft" feature, we can add a
  // visible control to allow explicit restoration.
  // Load categories into the category select so admin-created categories
  // (from category-management) show up in the Subject Category list.
  async function loadCategories() {
    try {
      const resp = await fetch('/admin/get_categories', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) return;
      const j = await resp.json().catch(() => ({}));
      const cats = (j && j.categories) || [];
      // clear select
      if (category) {
        category.innerHTML = '';
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'Select Category';
        category.appendChild(empty);
        cats.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.name;
          opt.textContent = c.name + (c.count ? ` (${c.count})` : '');
          category.appendChild(opt);
        });
      }
    } catch (e) {
      console.error('Failed to load categories', e);
    }
  }

  // call loadCategories on page ready
  loadCategories();
});
