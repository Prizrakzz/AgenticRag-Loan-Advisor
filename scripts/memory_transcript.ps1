# Memory Transcript Test Script - PowerShell
# Tests conversation continuity with memory-driven single agent

$ErrorActionPreference = "Stop"

# Configuration
$BaseUrl = "http://localhost:3000/api/v1"
$Credentials = @{
    "user_id" = "101"
    "password" = if ($env:TEST_PASSWORD) { $env:TEST_PASSWORD } else { "" }
}

Write-Host "🧪 Memory Transcript Test - PowerShell" -ForegroundColor Cyan
Write-Host "=" * 50

try {
    # Step 1: Login to get token
    Write-Host "`n🔐 Step 1: Authenticating..." -ForegroundColor Yellow
    
    $loginBody = @{
        "user_id" = $Credentials.user_id
        "password" = $Credentials.password
    } | ConvertTo-Json
    
    $loginResponse = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResponse.access_token
    
    if (-not $token) {
        throw "Failed to get authentication token"
    }
    
    Write-Host "✅ Authentication successful" -ForegroundColor Green
    
    # Headers for authenticated requests
    $headers = @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    }
    
    # Step 2: Turn 1 - Policy question (should return INFORM with references)
    Write-Host "`n📋 Step 2: Turn 1 - Policy Question" -ForegroundColor Yellow
    
    $turn1Body = @{
        "question" = "What are the interest rates on commercial loans?"
    } | ConvertTo-Json
    
    $turn1Response = Invoke-RestMethod -Uri "$BaseUrl/decision" -Method POST -Body $turn1Body -Headers $headers
    
    Write-Host "Question: What are the interest rates on commercial loans?"
    Write-Host "Decision: $($turn1Response.decision)" -ForegroundColor Magenta
    Write-Host "Answer: $($turn1Response.answer.Substring(0, [Math]::Min(100, $turn1Response.answer.Length)))..." -ForegroundColor White
    Write-Host "References: $($turn1Response.references.Count)" -ForegroundColor Cyan
    
    # Validate Turn 1
    if ($turn1Response.decision -ne "INFORM") {
        Write-Host "❌ FAIL: Expected decision=INFORM, got $($turn1Response.decision)" -ForegroundColor Red
        exit 1
    }
    
    if ($turn1Response.references.Count -eq 0) {
        Write-Host "❌ FAIL: Expected references.length >= 1, got 0" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Turn 1 validation passed" -ForegroundColor Green
    
    # Step 3: Turn 2 - Follow-up question (should maintain INFORM decision)
    Write-Host "`n🔄 Step 3: Turn 2 - Follow-up Question" -ForegroundColor Yellow
    
    $turn2Body = @{
        "question" = "are you sure?"
    } | ConvertTo-Json
    
    $turn2Response = Invoke-RestMethod -Uri "$BaseUrl/decision" -Method POST -Body $turn2Body -Headers $headers
    
    Write-Host "Question: are you sure?"
    Write-Host "Decision: $($turn2Response.decision)" -ForegroundColor Magenta
    Write-Host "Answer: $($turn2Response.answer.Substring(0, [Math]::Min(100, $turn2Response.answer.Length)))..." -ForegroundColor White
    Write-Host "References: $($turn2Response.references.Count)" -ForegroundColor Cyan
    
    # Validate Turn 2 - should maintain same decision type
    if ($turn2Response.decision -ne $turn1Response.decision) {
        Write-Host "❌ FAIL: Decision flipped without new content. Turn 1: $($turn1Response.decision), Turn 2: $($turn2Response.decision)" -ForegroundColor Red
        exit 1
    }
    
    if ($turn2Response.references.Count -eq 0 -and $turn1Response.references.Count -gt 0) {
        Write-Host "⚠️  WARNING: References disappeared in Turn 2" -ForegroundColor Yellow
    }
    
    Write-Host "✅ Turn 2 validation passed" -ForegroundColor Green
    
    # Step 4: Check response headers for decision engine
    Write-Host "`n🔍 Step 4: Checking Response Headers" -ForegroundColor Yellow
    
    # Note: PowerShell Invoke-RestMethod doesn't easily expose response headers
    # We'll use Invoke-WebRequest for this check
    $turn3Body = @{
        "question" = "test header check"
    } | ConvertTo-Json
    
    try {
        $webResponse = Invoke-WebRequest -Uri "$BaseUrl/decision" -Method POST -Body $turn3Body -Headers $headers
        $engineHeader = $webResponse.Headers["X-Decision-Engine"]
        
        if ($engineHeader -eq "single_agent") {
            Write-Host "✅ Response header X-Decision-Engine: single_agent" -ForegroundColor Green
        } else {
            Write-Host "⚠️  WARNING: Expected X-Decision-Engine: single_agent, got: $engineHeader" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️  WARNING: Could not check response headers: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    # Summary
    Write-Host "`n" + "=" * 50
    Write-Host "📊 Test Results Summary" -ForegroundColor Cyan
    Write-Host "=" * 50
    Write-Host "✅ Turn 1 (Policy Question): PASS" -ForegroundColor Green
    Write-Host "✅ Turn 2 (Follow-up): PASS" -ForegroundColor Green
    Write-Host "✅ Decision Consistency: PASS" -ForegroundColor Green
    Write-Host "✅ Memory-driven conversation: WORKING" -ForegroundColor Green
    
    Write-Host "`n🎉 All tests passed! Memory transcript system is working." -ForegroundColor Green
    exit 0

} catch {
    Write-Host "`n❌ Test failed with error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor Red
    exit 1
}
