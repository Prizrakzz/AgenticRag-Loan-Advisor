# PowerShell test script for anti-hedging eligibility decisions
# Tests that eligibility responses are decisive without hedging phrases

Write-Host "=== Anti-Hedging Eligibility Test (PowerShell) ===" -ForegroundColor Green

$baseUrl = "http://localhost:3000/api"

# Step 1: Login
try {
    $loginBody = @{
        user_id = "101"
    password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
    $loginResponse = Invoke-RestMethod -Uri "$baseUrl/v1/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResponse.access_token
    Write-Host "✓ Login successful" -ForegroundColor Green
} catch {
    Write-Host "✗ Login failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 2: Test eligibility question
try {
    $headers = @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    }
    
    $decisionBody = @{
        question = "Am I eligible for a `$25,000 car loan?"
    } | ConvertTo-Json

    $decisionResponse = Invoke-RestMethod -Uri "$baseUrl/v1/decision" -Method POST -Body $decisionBody -Headers $headers
    
    # Check response
    $decision = $decisionResponse.decision
    $answer = $decisionResponse.answer
    $answerPreview = $answer.Substring(0, [Math]::Min(120, $answer.Length))
    
    Write-Host "Decision: $decision" -ForegroundColor Cyan
    Write-Host "Answer preview: $answerPreview..." -ForegroundColor White
    
    # Validate decision type
    if ($decision -notin @("APPROVE", "DECLINE", "COUNTER")) {
        Write-Host "✗ Invalid decision type: $decision" -ForegroundColor Red
        exit 1
    }
    
    # Check for hedging if APPROVE/DECLINE
    if ($decision -in @("APPROVE", "DECLINE")) {
        $hedgingPhrases = @("depend on", "depends on", "will depend", "may vary", "cannot determine", "insufficient", "need more details", "specific policies")
        $answerLower = $answer.ToLower()
        
        $hedgingFound = $false
        foreach ($phrase in $hedgingPhrases) {
            if ($answerLower.Contains($phrase)) {
                Write-Host "✗ Hedging phrase detected: '$phrase'" -ForegroundColor Red
                $hedgingFound = $true
            }
        }
        
        if (-not $hedgingFound) {
            Write-Host "✓ No hedging detected in decisive answer" -ForegroundColor Green
        } else {
            exit 1
        }
    } else {
        Write-Host "✓ COUNTER decision (acceptable when data missing)" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "✗ Decision request failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "=== All tests PASSED ===" -ForegroundColor Green
