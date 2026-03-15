# Frontend E2E Smoke Test - PowerShell
# Tests all API endpoints through Next.js proxy on localhost:3000

Write-Host "🔥 Frontend E2E Smoke Test" -ForegroundColor Yellow
Write-Host "Testing API proxy through http://localhost:3000" -ForegroundColor Cyan

$BASE_URL = "http://localhost:3000"
$testResults = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Path,
        [hashtable]$Body = $null,
        [hashtable]$AdditionalHeaders = @{}
    )
    
    Write-Host "`n🧪 Testing: $Name" -ForegroundColor Yellow
    Write-Host "📡 $Method $Path" -ForegroundColor Cyan
    
    try {
        $headers = @{
            "Content-Type" = "application/json"
            "Accept" = "application/json"
        }
        
        foreach ($header in $AdditionalHeaders.GetEnumerator()) {
            $headers[$header.Key] = $header.Value
        }
        
        $uri = "$BASE_URL$Path"
        $params = @{
            Uri = $uri
            Method = $Method
            Headers = $headers
            TimeoutSec = 30
        }
        
        if ($Body) {
            $jsonBody = $Body | ConvertTo-Json -Depth 10
            $params.Body = $jsonBody
        }
        
        $response = Invoke-RestMethod @params
        
        Write-Host "✅ Status: 200 OK" -ForegroundColor Green
        return @{
            Success = $true
            Data = $response
            Error = $null
        }
        
    } catch {
        Write-Host "❌ Failed: $($_.Exception.Message)" -ForegroundColor Red
        return @{
            Success = $false
            Data = $null
            Error = $_.Exception.Message
        }
    }
}

# Test 1: Health Check
Write-Host "`n=== Test 1: Health Check ===" -ForegroundColor Blue
$healthResult = Test-Endpoint -Name "Health Check" -Method "GET" -Path "/api/health"

if ($healthResult.Success) {
    $health = $healthResult.Data
    Write-Host "🏥 Status: $($health.status)" -ForegroundColor Green
    Write-Host "🤖 Single Agent: $($health.single_agent)" -ForegroundColor Cyan
    Write-Host "📊 RAG Ready: $($health.rag_ready)" -ForegroundColor Cyan
    $testResults += @{test="Health"; status="PASS"}
} else {
    Write-Host "❌ Health check failed" -ForegroundColor Red
    $testResults += @{test="Health"; status="FAIL"}
    exit 1
}

# Test 2: Login
Write-Host "`n=== Test 2: Login ===" -ForegroundColor Blue
$loginBody = @{
    user_id = "101"
    password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
}

$loginResult = Test-Endpoint -Name "User Login" -Method "POST" -Path "/api/v1/auth/login" -Body $loginBody

$token = $null
if ($loginResult.Success) {
    $login = $loginResult.Data
    $token = $login.access_token
    Write-Host "🔐 Login successful" -ForegroundColor Green
    Write-Host "🎫 Token received" -ForegroundColor Cyan
    $testResults += @{test="Login"; status="PASS"}
} else {
    Write-Host "❌ Login failed" -ForegroundColor Red
    $testResults += @{test="Login"; status="FAIL"}
    # Continue without token for other tests
}

# Test 3: INFORM Decision (requires auth)
if ($token) {
    Write-Host "`n=== Test 3: INFORM Decision ===" -ForegroundColor Blue
    $authHeaders = @{
        "Authorization" = "Bearer $token"
    }
    
    $informBody = @{
        question = "What are the eligibility requirements for commercial loans?"
    }
    
    $informResult = Test-Endpoint -Name "INFORM Decision" -Method "POST" -Path "/api/v1/decision" -Body $informBody -AdditionalHeaders $authHeaders
    
    if ($informResult.Success) {
        $inform = $informResult.Data
        Write-Host "🎯 Decision: $($inform.decision)" -ForegroundColor Green
        $answerPreview = $inform.answer.Substring(0, [Math]::Min(100, $inform.answer.Length))
        Write-Host "💬 Answer: $answerPreview..." -ForegroundColor White
        Write-Host "📋 References: $($inform.references.Count)" -ForegroundColor Cyan
        
        if ($inform.decision -eq "INFORM" -and $inform.references.Count -gt 0) {
            $testResults += @{test="INFORM"; status="PASS"}
        } else {
            Write-Host "⚠️ Expected INFORM with references" -ForegroundColor Yellow
            $testResults += @{test="INFORM"; status="PARTIAL"}
        }
    } else {
        $testResults += @{test="INFORM"; status="FAIL"}
    }
} else {
    Write-Host "`n⏭️ Skipping INFORM test (no auth token)" -ForegroundColor Yellow
    $testResults += @{test="INFORM"; status="SKIP"}
}

# Test 4: Eligibility Decision (requires auth)
if ($token) {
    Write-Host "`n=== Test 4: Eligibility Decision ===" -ForegroundColor Blue
    $authHeaders = @{
        "Authorization" = "Bearer $token"
    }
    
    $eligibilityBody = @{
        question = "Am I eligible for a loan with 600 credit score and 50000 income?"
        customer_data = @{
            credit_score = 600
            annual_income = 50000
            employment_status = "employed"
            debt_to_income_ratio = 0.3
        }
    }
    
    $eligibilityResult = Test-Endpoint -Name "Eligibility Decision" -Method "POST" -Path "/api/v1/decision" -Body $eligibilityBody -AdditionalHeaders $authHeaders
    
    if ($eligibilityResult.Success) {
        $eligibility = $eligibilityResult.Data
        Write-Host "🎯 Decision: $($eligibility.decision)" -ForegroundColor Green
        $answerPreview = $eligibility.answer.Substring(0, [Math]::Min(100, $eligibility.answer.Length))
        Write-Host "💬 Answer: $answerPreview..." -ForegroundColor White
        Write-Host "📋 References: $($eligibility.references.Count)" -ForegroundColor Cyan
        
        $validDecisions = @("APPROVE", "DECLINE", "COUNTER", "INFORM")
        if ($eligibility.decision -in $validDecisions) {
            $testResults += @{test="Eligibility"; status="PASS"}
        } else {
            $testResults += @{test="Eligibility"; status="FAIL"}
        }
    } else {
        $testResults += @{test="Eligibility"; status="FAIL"}
    }
} else {
    Write-Host "`n⏭️ Skipping Eligibility test (no auth token)" -ForegroundColor Yellow
    $testResults += @{test="Eligibility"; status="SKIP"}
}

# Summary
Write-Host "`n📊 SMOKE TEST RESULTS" -ForegroundColor Yellow
$passCount = ($testResults | Where-Object {$_.status -eq "PASS"}).Count
$totalTests = $testResults.Count

foreach ($result in $testResults) {
    $color = switch ($result.status) {
        "PASS" { "Green" }
        "FAIL" { "Red" }
        "PARTIAL" { "Yellow" }
        "SKIP" { "Gray" }
    }
    Write-Host "$($result.test): $($result.status)" -ForegroundColor $color
}

Write-Host "`nPassed: $passCount/$totalTests" -ForegroundColor $(if($passCount -eq $totalTests) {"Green"} else {"Yellow"})

if ($passCount -eq $totalTests) {
    Write-Host "`n🎉 ALL TESTS PASSED!" -ForegroundColor Green
    Write-Host "✅ Next.js proxy working correctly" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n⚠️ SOME TESTS FAILED" -ForegroundColor Yellow
    exit 1
}
