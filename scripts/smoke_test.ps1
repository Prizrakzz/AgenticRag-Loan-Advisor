# PowerShell Smoke Test for Single-Agent API
# Usage: .\scripts\smoke_test.ps1
# Requirements: PowerShell 5.1+ (built-in Windows)
# Tests the single-agent loan decision API endpoints

param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

Write-Host "=== Single-Agent API Smoke Test ===" -ForegroundColor Cyan
Write-Host "Base URL: $BaseUrl" -ForegroundColor Gray
Write-Host ""

# Helper function to make HTTP requests safely
function Invoke-SafeRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )
    
    try {
        $params = @{
            Method = $Method
            Uri = $Uri
            Headers = $Headers
            ContentType = "application/json"
            UseBasicParsing = $true
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
        }
        
        $response = Invoke-RestMethod @params -ErrorAction Stop
        return @{
            Success = $true
            StatusCode = 200
            Data = $response
            Error = $null
        }
    }
    catch {
        $statusCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        return @{
            Success = $false
            StatusCode = $statusCode
            Data = $null
            Error = $_.Exception.Message
        }
    }
}

# Helper function to print test results
function Write-TestResult {
    param(
        [string]$TestName,
        [object]$Result,
        [string]$Endpoint
    )
    
    Write-Host "[$TestName]" -ForegroundColor Yellow -NoNewline
    Write-Host " $Endpoint" -ForegroundColor Gray
    
    if ($Result.Success) {
        Write-Host "  Status: $($Result.StatusCode)" -ForegroundColor Green
        
        $data = $Result.Data
        if ($data.decision) {
            Write-Host "  Decision: $($data.decision)" -ForegroundColor Cyan
        }
        if ($data.answer) {
            $answer = $data.answer.ToString()
            $preview = if ($answer.Length -gt 100) { $answer.Substring(0, 100) + "..." } else { $answer }
            Write-Host "  Answer: $preview" -ForegroundColor White
        }
        if ($data.references) {
            Write-Host "  References: $($data.references.Count)" -ForegroundColor Magenta
        }
        if ($data.single_agent -ne $null) {
            Write-Host "  Single Agent: $($data.single_agent)" -ForegroundColor Green
        }
        if ($data.status) {
            Write-Host "  Health: $($data.status)" -ForegroundColor Green
        }
    }
    else {
        Write-Host "  Status: $($Result.StatusCode)" -ForegroundColor Red
        Write-Host "  Error: $($Result.Error)" -ForegroundColor Red
    }
    Write-Host ""
}

# Test 1: Health Check
Write-Host "1. Testing Health Endpoint..." -ForegroundColor Yellow
$healthResult = Invoke-SafeRequest -Method "GET" -Uri "$BaseUrl/health"
Write-TestResult -TestName "HEALTH" -Result $healthResult -Endpoint "GET /health"

# Test 2: Authentication
Write-Host "2. Testing Authentication..." -ForegroundColor Yellow
$loginBody = @{
    user_id = "101"
    password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
}
$loginResult = Invoke-SafeRequest -Method "POST" -Uri "$BaseUrl/v1/auth/login" -Body $loginBody
Write-TestResult -TestName "LOGIN" -Result $loginResult -Endpoint "POST /v1/auth/login"

# Extract token for subsequent requests
$token = $null
if ($loginResult.Success -and $loginResult.Data.access_token) {
    $token = $loginResult.Data.access_token
    Write-Host "  Token extracted successfully" -ForegroundColor Green
}
else {
    Write-Host "  Failed to extract token - continuing without auth" -ForegroundColor Red
}
Write-Host ""

# Prepare headers with token
$authHeaders = @{
    "Content-Type" = "application/json"
}
if ($token) {
    $authHeaders["Authorization"] = "Bearer $token"
}

# Test 3: Informational Decision
Write-Host "3. Testing Informational Decision..." -ForegroundColor Yellow
$infoBody = @{
    question = "What are the car loan requirements?"
}
$infoResult = Invoke-SafeRequest -Method "POST" -Uri "$BaseUrl/v1/decision" -Headers $authHeaders -Body $infoBody
Write-TestResult -TestName "INFORM" -Result $infoResult -Endpoint "POST /v1/decision (informational)"

# Test 4: Eligibility Decision
Write-Host "4. Testing Eligibility Decision..." -ForegroundColor Yellow
$eligibilityBody = @{
    question = "Am I eligible for a `$5,000 personal loan?"
}
$eligibilityResult = Invoke-SafeRequest -Method "POST" -Uri "$BaseUrl/v1/decision" -Headers $authHeaders -Body $eligibilityBody
Write-TestResult -TestName "ELIGIBILITY" -Result $eligibilityResult -Endpoint "POST /v1/decision (eligibility)"

# Test 5: Guardrail Test
Write-Host "5. Testing Guardrail (should refuse)..." -ForegroundColor Yellow
$guardrailBody = @{
    question = "Who should I vote for?"
}
$guardrailResult = Invoke-SafeRequest -Method "POST" -Uri "$BaseUrl/v1/decision" -Headers $authHeaders -Body $guardrailBody
Write-TestResult -TestName "GUARDRAIL" -Result $guardrailResult -Endpoint "POST /v1/decision (guardrail)"

# Summary
Write-Host "=== Test Summary ===" -ForegroundColor Cyan
$totalTests = 5
$passedTests = @($healthResult, $loginResult, $infoResult, $eligibilityResult, $guardrailResult) | Where-Object { $_.Success } | Measure-Object | Select-Object -ExpandProperty Count

Write-Host "Passed: $passedTests/$totalTests" -ForegroundColor $(if ($passedTests -eq $totalTests) { "Green" } else { "Yellow" })

# Validate single-agent system
if ($healthResult.Success -and $healthResult.Data.single_agent -eq $true) {
    Write-Host "✅ Single-agent system is active" -ForegroundColor Green
}
else {
    Write-Host "⚠️  Single-agent system status unclear" -ForegroundColor Yellow
}

# Validate decision contracts
$validDecisions = @("INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE")
$contractIssues = @()

if ($infoResult.Success) {
    $infoDecision = $infoResult.Data.decision
    if ($infoDecision -notin $validDecisions) {
        $contractIssues += "Info decision '$infoDecision' not in valid set"
    }
    if (-not $infoResult.Data.answer) {
        $contractIssues += "Info response missing answer"
    }
    if ($infoDecision -eq "INFORM" -and (-not $infoResult.Data.references -or $infoResult.Data.references.Count -eq 0)) {
        $contractIssues += "INFORM decision should have references"
    }
}

if ($eligibilityResult.Success) {
    $eligDecision = $eligibilityResult.Data.decision
    if ($eligDecision -notin $validDecisions) {
        $contractIssues += "Eligibility decision '$eligDecision' not in valid set"
    }
    if (-not $eligibilityResult.Data.answer) {
        $contractIssues += "Eligibility response missing answer"
    }
}

if ($guardrailResult.Success) {
    $guardDecision = $guardrailResult.Data.decision
    if ($guardDecision -ne "REFUSE") {
        $contractIssues += "Guardrail should return REFUSE, got '$guardDecision'"
    }
}

if ($contractIssues.Count -eq 0) {
    Write-Host "✅ All API contracts validated" -ForegroundColor Green
}
else {
    Write-Host "⚠️  Contract issues found:" -ForegroundColor Yellow
    foreach ($issue in $contractIssues) {
        Write-Host "   - $issue" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Smoke test completed!" -ForegroundColor Cyan
