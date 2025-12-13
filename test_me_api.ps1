# Test /api/v1/me/student endpoint

# Prerequisites: Flask server must be running
# Run: flask run  or  python wsgi.py

$baseUrl = "http://127.0.0.1:5000"

# Login to get token
$loginPayload = @{
    email = "aayush@gmail.com"
    password = "test123"
} | ConvertTo-Json

Write-Host "Logging in..." -ForegroundColor Cyan
$loginResp = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method POST -Body $loginPayload -ContentType "application/json" -ErrorAction Stop

if ($loginResp.success) {
    Write-Host "Login successful" -ForegroundColor Green
    $token = $loginResp.access_token
    
    # Test PUT /api/v1/me/student
    $headers = @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    }
    
    $updatePayload = @{
        name = "PowerShell Test Update"
        mobile = "9876543210"
        class = "Grade 10"
    } | ConvertTo-Json
    
    Write-Host ""
    Write-Host "Updating student profile..." -ForegroundColor Cyan
    Write-Host "Payload: $updatePayload"
    
    try {
        $updateResp = Invoke-RestMethod -Uri "$baseUrl/api/v1/me/student" -Method PUT -Headers $headers -Body $updatePayload -ContentType "application/json"
        
        Write-Host ""
        Write-Host "Success!" -ForegroundColor Green
        Write-Host "Response: $($updateResp | ConvertTo-Json)"
    }
    catch {
        Write-Host ""
        Write-Host "Failed" -ForegroundColor Red
        Write-Host "Error: $_"
        if ($_.ErrorDetails) {
            Write-Host "Details: $($_.ErrorDetails.Message)"
        }
    }
}
else {
    Write-Host "Login failed" -ForegroundColor Red
    Write-Host $loginResp
}
