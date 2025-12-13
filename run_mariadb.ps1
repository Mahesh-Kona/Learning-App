# Run Flask app with MariaDB
$env:DATABASE_URL = "mysql+pymysql://root:@localhost:3306/learning?charset=utf8mb4"
$env:FLASK_APP = "wsgi.py"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "True"

Write-Host "Starting Flask app with MariaDB..." -ForegroundColor Green
Write-Host "Database: mysql://root@localhost:3306/learning" -ForegroundColor Cyan
Write-Host ""

& .\venv\Scripts\python.exe wsgi.py
