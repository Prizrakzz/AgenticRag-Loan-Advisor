# PowerShell Smoke Test for Frontend API (ROBUST VERSION)
# Tests eligibility requirements (no 400 errors) and references display

$BASE = "http://localhost:3000/api"
$ErrorActionPreference = "Continue"  # Don't stop on first error

Write-Host "=== Frontend API Smoke Test (PowerShell) - Robust Edition ===" -ForegroundColor Green

$allPassed = $true

try {
    # Test 1: Health check
    Write-Host "[GET] /health" -ForegroundColor Yellow
    $healthResponse = Invoke-RestMethod -Uri "$BASE/health" -Method GET -TimeoutSec 10
    Write-Host "✓ Health Status: $($healthResponse.status)" -ForegroundColor Green
    
    # Test 2: Login
    Write-Host "[POST] /v1/auth/login" -ForegroundColor Yellow
    $loginBody = @{
        user_id = "101"
        password = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
    } | ConvertTo-Json
    
    $loginResponse = Invoke-RestMethod -Uri "$BASE/v1/auth/login" -Method POST -Body $loginBody -ContentType "application/json" -TimeoutSec 10
    $token = $loginResponse.access_token
    Write-Host "✓ Login successful, token obtained" -ForegroundColor Green
    
    # Headers for authenticated requests
    $headers = @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    }
    
    # Test 3: Informational query (must have references)
    Write-Host "[POST] /v1/decision - Informational" -ForegroundColor Yellow
    $infoBody = @{
        question = "What are the eligibility requirements?"
    } | ConvertTo-Json
    
    try {
        $infoResponse = Invoke-RestMethod -Uri "$BASE/v1/decision" -Method POST -Body $infoBody -Headers $headers -TimeoutSec 30
        
        Write-Host "Decision: $($infoResponse.decision)" -ForegroundColor Cyan
        Write-Host "Answer length: $($infoResponse.answer.Length)" -ForegroundColor Cyan
        Write-Host "References count: $($infoResponse.references.Count)" -ForegroundColor Cyan
        
        # Validate INFORM response
        if ($infoResponse.decision -eq "INFORM") {
            if ($infoResponse.references.Count -ge 1) {
                Write-Host "✓ INFORM response has references" -ForegroundColor Green
                
                # Check for references line in metadata
                if ($infoResponse.metadata -and $infoResponse.metadata.references_line) {
                    Write-Host "✓ References line: $($infoResponse.metadata.references_line)" -ForegroundColor Green
                } else {
                    # Synthesize references line
                    $refParts = @()
                    foreach ($ref in $infoResponse.references) {
                        $refParts += "$($ref.source) — $($ref.section) (p.$($ref.page))"
                    }
                    $referencesLine = "References: " + ($refParts -join "; ")
                    Write-Host "✓ Synthesized references: $referencesLine" -ForegroundColor Green
                }
            } else {
                Write-Host "✗ INFORM response missing references" -ForegroundColor Red
                $allPassed = $false
            }
        } else {
            Write-Host "✗ Expected INFORM decision, got: $($infoResponse.decision)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "✗ Informational test failed: $($_.Exception.Message)" -ForegroundColor Red
        $allPassed = $false
    }
    
    # Test 4: Eligibility query (must not return 400)
    Write-Host "[POST] /v1/decision - Eligibility" -ForegroundColor Yellow
    $eligibilityBody = @{
        question = "Am I eligible for a $25000 car loan?"
    } | ConvertTo-Json
    
    try {
        $eligibilityResponse = Invoke-RestMethod -Uri "$BASE/v1/decision" -Method POST -Body $eligibilityBody -Headers $headers -TimeoutSec 30
        
        Write-Host "Decision: $($eligibilityResponse.decision)" -ForegroundColor Cyan
        Write-Host "Answer length: $($eligibilityResponse.answer.Length)" -ForegroundColor Cyan
        
        # Validate eligibility response
        $validDecisions = @("APPROVE", "DECLINE", "COUNTER")
        if ($eligibilityResponse.decision -in $validDecisions) {
            Write-Host "✓ Valid eligibility decision: $($eligibilityResponse.decision)" -ForegroundColor Green
            
            # If COUNTER, check for missing items
            if ($eligibilityResponse.decision -eq "COUNTER") {
                if ($eligibilityResponse.answer -match "(pay stubs|employment|DTI|documentation|verification)") {
                    Write-Host "✓ COUNTER response lists specific missing items" -ForegroundColor Green
                } else {
                    Write-Host "! COUNTER response should list specific missing items" -ForegroundColor Yellow
                }
            }
            
            # Check answer is non-empty
            if ($eligibilityResponse.answer.Length -gt 10) {
                Write-Host "✓ Non-empty answer provided" -ForegroundColor Green
            } else {
                Write-Host "✗ Answer too short or empty" -ForegroundColor Red
                $allPassed = $false
            }
        } else {
            Write-Host "✗ Invalid eligibility decision: $($eligibilityResponse.decision)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "✗ Eligibility test failed: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
            Write-Host "HTTP Status: $statusCode" -ForegroundColor Red
            if ($statusCode -eq 400) {
                Write-Host "✗✗ CRITICAL: Got 400 error on eligibility request - this should be fixed!" -ForegroundColor Red
            }
        }
        $allPassed = $false
    }
    
    if ($allPassed) {
        Write-Host "`n=== All Tests Passed ===" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "`n=== Some Tests Failed ===" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "✗ Critical test failure: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
