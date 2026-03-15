# Frontend E2E Smoke Test - PowerShell
# Tests all API endpoints through Next.js proxy on localhost:3000

Write-Host "Frontend E2E Smoke Test" -ForegroundColor Yellow
Write-Host "Testing API proxy through http://localhost:3000" -ForegroundColor Cyan

$BASE_URL = "http://localhost:3000"
$testResults = @()

# Test 1: Health Check
Write-Host "`nTest 1: Health Check" -ForegroundColor Blue
try {
    $health = Invoke-RestMethod -Uri "$BASE_URL/api/health" -Method GET
    Write-Host "Health Status: $($health.status)" -ForegroundColor Green
    Write-Host "Single Agent: $($health.single_agent)" -ForegroundColor Green
    Write-Host "RAG Ready: $($health.rag_ready)" -ForegroundColor Cyan
    $testResults += @{Test="Health"; Status="PASS"}
} catch {
    Write-Host "Health check failed: $($_.Exception.Message)" -ForegroundColor Red
    $testResults += @{Test="Health"; Status="FAIL"}
}

# Test 2: Login
Write-Host "`nTest 2: Login" -ForegroundColor Blue
$loginBody = @{
    user_id = "12345"
    password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
} | ConvertTo-Json

try {
    $login = Invoke-RestMethod -Uri "$BASE_URL/api/v1/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    Write-Host "Login successful, token received" -ForegroundColor Green
    $token = $login.access_token
    $testResults += @{Test="Login"; Status="PASS"}
} catch {
    Write-Host "Login failed: $($_.Exception.Message)" -ForegroundColor Red
    $token = "mock_token"
    $testResults += @{Test="Login"; Status="FAIL"}
}

# Test 3: Informational Decision
Write-Host "`nTest 3: Informational Decision" -ForegroundColor Blue
$informBody = @{
    question = "What are the car loan requirements?"
    autonomous = $true
    client_id = 12345
} | ConvertTo-Json

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

try {
    $decision = Invoke-RestMethod -Uri "$BASE_URL/api/v1/decision" -Method POST -Body $informBody -Headers $headers
    Write-Host "Decision: $($decision.decision)" -ForegroundColor Green
    Write-Host "Answer length: $($decision.answer.Length)" -ForegroundColor Cyan
    Write-Host "References count: $($decision.references.Count)" -ForegroundColor Cyan
    
    if ($decision.references -and $decision.references.Count -gt 0) {
        for ($i = 0; $i -lt [Math]::Min(3, $decision.references.Count); $i++) {
            $ref = $decision.references[$i]
            Write-Host "  S$($i+1): $($ref.section) (page $($ref.page))" -ForegroundColor Gray
        }
    }
    
    $testResults += @{Test="Informational"; Status="PASS"}
} catch {
    Write-Host "Informational decision failed: $($_.Exception.Message)" -ForegroundColor Red
    $testResults += @{Test="Informational"; Status="FAIL"}
}

# Test 4: Eligibility Decision
Write-Host "`nTest 4: Eligibility Decision" -ForegroundColor Blue
$eligibilityBody = @{
    question = "Am I eligible for a 5000 dollar personal loan?"
    autonomous = $true
    client_id = 12345
} | ConvertTo-Json

try {
    $decision = Invoke-RestMethod -Uri "$BASE_URL/api/v1/decision" -Method POST -Body $eligibilityBody -Headers $headers
    Write-Host "Decision: $($decision.decision)" -ForegroundColor Green
    Write-Host "Answer length: $($decision.answer.Length)" -ForegroundColor Cyan
    Write-Host "References count: $($decision.references.Count)" -ForegroundColor Cyan
    
    if ($decision.references -and $decision.references.Count -gt 0) {
        for ($i = 0; $i -lt [Math]::Min(3, $decision.references.Count); $i++) {
            $ref = $decision.references[$i]
            Write-Host "  S$($i+1): $($ref.section) (page $($ref.page))" -ForegroundColor Gray
        }
    }
    
    $testResults += @{Test="Eligibility"; Status="PASS"}
} catch {
    Write-Host "Eligibility decision failed: $($_.Exception.Message)" -ForegroundColor Red
    $testResults += @{Test="Eligibility"; Status="FAIL"}
}

# Summary
Write-Host "`nTEST RESULTS SUMMARY" -ForegroundColor Yellow
$passCount = ($testResults | Where-Object {$_.Status -eq "PASS"}).Count
$totalTests = $testResults.Count

foreach ($result in $testResults) {
    $color = if ($result.Status -eq "PASS") {"Green"} else {"Red"}
    Write-Host "$($result.Test): $($result.Status)" -ForegroundColor $color
}

Write-Host "`nResults: $passCount/$totalTests tests passed" -ForegroundColor $(if($passCount -eq $totalTests) {"Green"} else {"Yellow"})

if ($passCount -eq $totalTests) {
    Write-Host "`nALL TESTS PASSED - Frontend proxy working correctly!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nSOME TESTS FAILED - Check configuration" -ForegroundColor Yellow
    exit 1
}
