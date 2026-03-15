# Frontend Smoke Test (PowerShell)
# How to run: powershell -ExecutionPolicy Bypass -File .\scripts\smoke_frontend.ps1

$BASE_URL = "http://localhost:3000/api"
$TIMEOUT = 10
$ExitCode = 0

Write-Host "=== Frontend Proxy Smoke Test ===" -ForegroundColor Cyan
Write-Host "Base URL: $BASE_URL" -ForegroundColor Gray

function Test-Endpoint {
    param(
        [string]$Method,
        [string]$Endpoint,
        [hashtable]$Body = $null,
        [hashtable]$Headers = @{},
        [string]$Description
    )
    
    Write-Host "`n[$Method] $Endpoint" -ForegroundColor Yellow
    Write-Host "Test: $Description" -ForegroundColor Gray
    
    try {
        $uri = "$BASE_URL$Endpoint"
        $params = @{
            Uri = $uri
            Method = $Method
            TimeoutSec = $TIMEOUT
            Headers = $Headers
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
            $params.ContentType = "application/json"
        }
        
        $response = Invoke-RestMethod @params
        Write-Host "✓ Status: 200 OK" -ForegroundColor Green
        return $response
    }
    catch {
        Write-Host "✗ Failed: $($_.Exception.Message)" -ForegroundColor Red
        $global:ExitCode = 1
        return $null
    }
}

function Test-Schema {
    param($Response, [string]$TestName)
    
    $errors = @()
    
    # Check decision field
    if (-not $Response.decision) {
        $errors += "Missing 'decision' field"
    } elseif ($Response.decision -notin @("INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE")) {
        $errors += "Invalid decision: $($Response.decision)"
    }
    
    # Check answer field for non-REFUSE decisions
    if ($Response.decision -ne "REFUSE") {
        if (-not $Response.answer -or $Response.answer.Length -eq 0) {
            $errors += "Missing or empty 'answer' field for $($Response.decision)"
        }
    }
    
    # Check references field
    if (-not $Response.PSObject.Properties.Name -contains "references") {
        $errors += "Missing 'references' field"
    } elseif ($Response.references -isnot [array]) {
        $errors += "'references' is not an array"
    } elseif ($Response.decision -eq "INFORM" -and $Response.references.Count -eq 0) {
        $errors += "INFORM decision should have references.length ≥ 1, got $($Response.references.Count)"
    }
    
    if ($errors.Count -eq 0) {
        Write-Host "✓ Schema valid" -ForegroundColor Green
    } else {
        Write-Host "✗ Schema errors:" -ForegroundColor Red
        foreach ($error in $errors) {
            Write-Host "  - $error" -ForegroundColor Red
        }
        $global:ExitCode = 1
    }
}

function Show-ResponseSummary {
    param($Response, [string]$TestName)
    
    if (-not $Response) { return }
    
    $answer = if ($Response.answer) { 
        if ($Response.answer.Length -gt 120) { 
            $Response.answer.Substring(0, 120) + "..." 
        } else { 
            $Response.answer 
        }
    } else { 
        "(no answer)" 
    }
    
    Write-Host "Decision: $($Response.decision)" -ForegroundColor Cyan
    Write-Host "Answer: $answer" -ForegroundColor White
    Write-Host "References: $($Response.references.Count)" -ForegroundColor Gray
    
    # Show RAG debug info if available
    if ($Response.metadata -and $Response.metadata.rag_debug) {
        $rag = $Response.metadata.rag_debug
        Write-Host "RAG Debug: collection=$($rag.collection), query='$($rag.query)', snippets=$($rag.snippets_found)" -ForegroundColor Magenta
    }
}

# Test 1: Health Check
$health = Test-Endpoint -Method "GET" -Endpoint "/health" -Description "Health check"
if ($health) {
    Write-Host "Health status: OK" -ForegroundColor Green
}

# Test 2: Login
$loginBody = @{
    user_id = "101"
    password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
}
$loginResponse = Test-Endpoint -Method "POST" -Endpoint "/v1/auth/login" -Body $loginBody -Description "User authentication"

if (-not $loginResponse -or -not $loginResponse.access_token) {
    Write-Host "✗ Login failed - cannot continue with authenticated tests" -ForegroundColor Red
    $ExitCode = 1
} else {
    Write-Host "✓ Login successful" -ForegroundColor Green
    $authHeaders = @{
        "Authorization" = "Bearer $($loginResponse.access_token)"
    }
    
    # Test 3: Informational Decision
    $infoBody = @{
        question = "What are the car loan requirements?"
        autonomous = $true
    }
    $infoResponse = Test-Endpoint -Method "POST" -Endpoint "/v1/decision" -Body $infoBody -Headers $authHeaders -Description "Informational query"
    if ($infoResponse) {
        Test-Schema -Response $infoResponse -TestName "Informational"
        Show-ResponseSummary -Response $infoResponse -TestName "Informational"
    }
    
    # Test 4: Eligibility Decision
    $eligBody = @{
        question = "Am I eligible for a `$5,000 personal loan?"
        autonomous = $true
    }
    $eligResponse = Test-Endpoint -Method "POST" -Endpoint "/v1/decision" -Body $eligBody -Headers $authHeaders -Description "Eligibility query"
    if ($eligResponse) {
        Test-Schema -Response $eligResponse -TestName "Eligibility"
        Show-ResponseSummary -Response $eligResponse -TestName "Eligibility"
    }
}

# Summary
Write-Host "`n=== Test Summary ===" -ForegroundColor Cyan
if ($ExitCode -eq 0) {
    Write-Host "✓ All tests PASSED" -ForegroundColor Green
} else {
    Write-Host "✗ Some tests FAILED" -ForegroundColor Red
}

exit $ExitCode
