# API Endpoints (local dev)

Base URL: `http://127.0.0.1:5000`

Notes:
- Use the base URL above when running the dev server locally (`python wsgi.py`).
- Where path parameters are shown (e.g. `<int:id>`), replace with the actual value.
- Authentication: use `/api/v1/auth/login` to obtain a JWT; include `Authorization: Bearer <token>` for protected endpoints.

## Admin UI / Admin API (session-based admin pages)

- `GET /admin/login` — admin login page
- `POST /admin/login` — admin login (form/JSON)
- `GET /admin/dashboard` — admin dashboard
- `GET /admin/all_courses` — admin courses list page
- `GET /admin/all_topics` — admin topics page
- `GET /admin/category-management` — category UI

- `GET /admin/get_courses` — returns JSON `{courses: [...]}`
- `GET /admin/get_lessons?course_id=<id>` — list lessons for course
- `GET /admin/get_topic?id=<topic_id>` — get topic

- `POST /admin/create_category` — create category
- `POST /admin/delete_category` — delete category
- `POST /admin/rename_category` — rename category
- `POST /admin/clear_category` — clear category on courses

- `POST /admin/create_course` — create course (form or JSON)
- `POST /admin/update_course` — update course
- `POST /admin/delete_course` — delete course (or `DELETE`)

- `POST /admin/create_lesson` — create lesson
- `POST /admin/update_lesson` — update lesson
- `POST /admin/delete_lesson` — delete lesson

- `GET /admin/topic-editor/` and `GET /admin/topic-editor/<path:filename>` — serve topic-editor assets (if present)

## Public / API routes (JSON)

- `POST /api/v1/auth/login` — login (JSON) -> returns JWT
  - Example: `POST /api/v1/auth/login` body `{ "email": "...", "password": "..." }`
- `POST /api/v1/auth/register` — register new user
- `POST /api/v1/auth/refresh` — refresh token

- `GET /api/v1/courses` — list courses (JSON)
- `GET /api/v1/courses/<int:id>` — get course details
- `GET /api/v1/courses/<int:id>/lessons` — list lessons for a course

- `GET /api/v1/content/<int:lesson_id>` — get lesson content (cloud/lesson content)

- `GET /api/v1/lessons/<int:id>` — get lesson details
- `POST /api/v1/lessons` — create a lesson (protected)
- `PUT /api/v1/lessons/<int:id>` — update lesson (protected)

- `POST /api/v1/progress` — submit progress (protected)
  - Payload expected: progress fields (see backend model). After submit, server regenerates per-user JSON.

- `POST /api/v1/uploads` — upload file
- `POST /api/v1/uploads/presign` — get presigned upload info

- `GET /api/v1/debug/assets` — debug asset listing

## Static / Misc

- `GET /` — `home` (index page)
- `GET /demo` — demo page
- `GET /uploads/<path:filename>` — serve uploaded files
- `GET /static/<path:filename>` — static assets

## Cloud JSON serving route

- `GET /api/v1/cloud/<filename>` — serve pre-generated JSON artifacts from `instance/dynamic_json/`
  - Examples:
    - `GET /api/v1/cloud/courses.json`
    - `GET /api/v1/cloud/user_24_progress.json`

## Example requests (PowerShell)

```powershell
# List courses
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/courses" -Method GET | ConvertTo-Json -Depth 6

# Login and capture token
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/auth/login" -Method Post -Body (@{email='dev@local'; password='password'} | ConvertTo-Json) -ContentType 'application/json'
$token = $resp.access_token

# Call protected endpoint with token
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/progress" -Method Post -Body (@{lesson_id=1; percent=50} | ConvertTo-Json) -ContentType 'application/json' -Headers @{ Authorization = "Bearer $token" }
```

## Next steps / Tips for frontend dev

- Use the base URL above while testing locally. Replace `127.0.0.1` with your deployed host in staging/production.
- For endpoints that are session-based (admin UI), use browser-based requests or mimic cookies; for API JWT endpoints use the `Authorization` header.
- If you want, I can also export a Postman collection or OpenAPI/Swagger spec from these routes.

---
Generated on local dev. Adjust host/port if your server uses a different address/port.
