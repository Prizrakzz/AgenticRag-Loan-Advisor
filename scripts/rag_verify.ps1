# PowerShell RAG Verification Script
# Tests that single-agent uses existing Qdrant collection and returns references

param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = $env:TEST_PASSWORD
)

Write-Host "🔍 RAG Verification Script" -ForegroundColor Yellow
Write-Host "Testing auto-detection and reference generation..." -ForegroundColor Cyan

# Test cases that must return INFORM with references
$TestCases = @(
    @{
        "name" = "Eligibility Requirements"
        "question" = "What are the eligibility requirements?"
        "expected_decision" = "INFORM"
        "expected_section_contains" = "Eligibility"
    },
    @{
        "name" = "Collateral Requirements"  
        "question" = "Do you require collateral for commercial loans?"
        "expected_decision" = "INFORM"
        "expected_section_contains" = @("collateral", "loan", "commercial")
    }
)

function Get-AuthToken {
    param([string]$BaseUrl, [string]$Username, [string]$Password)
    
    try {
        $loginBody = @{
            username = $Username
            password = $Password
        } | ConvertTo-Json
        
        $headers = @{
            "Content-Type" = "application/json"
        }
        
        $response = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method POST -Body $loginBody -Headers $headers
        return $response.access_token
    }
    catch {
        Write-Host "❌ Login failed: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

function Test-SingleAgentResponse {
    param(
        [string]$BaseUrl,
        [string]$Token,
        [string]$Question,
        [string]$ExpectedDecision,
        [object]$ExpectedSectionContains
    )
    
    $headers = @{
        "Content-Type" = "application/json"
        "Authorization" = "Bearer $Token"
    }
    
    $body = @{
        question = $Question
        context = @{
            session_id = "rag_verify_$(Get-Date -Format 'yyyyMMddHHmmss')"
        }
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/ask" -Method POST -Body $body -Headers $headers
        
        # Validate decision
        $decision = $response.decision
        if ($decision -ne $ExpectedDecision) {
            Write-Host "❌ Wrong decision: expected $ExpectedDecision, got $decision" -ForegroundColor Red
            return $false
        }
        
        # Validate references exist
        $references = $response.references
        if (-not $references -or $references.Count -eq 0) {
            Write-Host "❌ No references found" -ForegroundColor Red
            return $false
        }
        
        # Validate reference structure
        $firstRef = $references[0]
        if (-not $firstRef.section -or -not $firstRef.page) {
            Write-Host "❌ Invalid reference structure" -ForegroundColor Red
            return $false
        }
        
        # Validate section content
        $sectionMatches = $false
        if ($ExpectedSectionContains -is [array]) {
            foreach ($term in $ExpectedSectionContains) {
                if ($firstRef.section -like "*$term*") {
                    $sectionMatches = $true
                    break
                }
            }
        } else {
            $sectionMatches = $firstRef.section -like "*$ExpectedSectionContains*"
        }
        
        if (-not $sectionMatches) {
            Write-Host "❌ Section doesn't match expected content: $($firstRef.section)" -ForegroundColor Red
            return $false
        }
        
        # Validate RAG debug metadata
        $ragDebug = $response.metadata.rag_debug
        if (-not $ragDebug -or -not $ragDebug.collection -or $ragDebug.snippets_found -eq 0) {
            Write-Host "❌ Missing or invalid RAG debug metadata" -ForegroundColor Red
            return $false
        }
        
        # Print results
        Write-Host "✅ Decision: $decision" -ForegroundColor Green
        Write-Host "✅ References: $($references.Count)" -ForegroundColor Green
        Write-Host "✅ Collection: $($ragDebug.collection)" -ForegroundColor Green
        Write-Host "✅ Snippets found: $($ragDebug.snippets_found)" -ForegroundColor Green
        
        # Print first 3 references
        Write-Host "📚 References:" -ForegroundColor Cyan
        for ($i = 0; $i -lt [Math]::Min(3, $references.Count); $i++) {
            $ref = $references[$i]
            Write-Host "  S$($i+1): $($ref.section) (page $($ref.page))" -ForegroundColor White
        }
        
        return $true
        
    } catch {
        Write-Host "❌ Request failed: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# Main execution
Write-Host "🔐 Authenticating..." -ForegroundColor Cyan
$token = Get-AuthToken -BaseUrl $BaseUrl -Username $Username -Password $Password

if (-not $token) {
    Write-Host "❌ Authentication failed. Exiting." -ForegroundColor Red
    exit 1
}

Write-Host "✅ Authentication successful" -ForegroundColor Green

$passCount = 0
$totalTests = $TestCases.Count

foreach ($testCase in $TestCases) {
    Write-Host "`n🧪 Testing: $($testCase.name)" -ForegroundColor Yellow
    Write-Host "❓ Question: $($testCase.question)" -ForegroundColor Gray
    
    $result = Test-SingleAgentResponse -BaseUrl $BaseUrl -Token $token -Question $testCase.question -ExpectedDecision $testCase.expected_decision -ExpectedSectionContains $testCase.expected_section_contains
    
    if ($result) {
        $passCount++
        Write-Host "✅ PASS" -ForegroundColor Green
    } else {
        Write-Host "❌ FAIL" -ForegroundColor Red
    }
}

# Summary
Write-Host "`n📊 VERIFICATION RESULTS" -ForegroundColor Yellow
Write-Host "Passed: $passCount/$totalTests" -ForegroundColor $(if($passCount -eq $totalTests) {"Green"} else {"Red"})

if ($passCount -eq $totalTests) {
    Write-Host "🎉 ALL TESTS PASSED - RAG auto-detection working!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "❌ SOME TESTS FAILED - Check RAG configuration" -ForegroundColor Red
    exit 1
}
