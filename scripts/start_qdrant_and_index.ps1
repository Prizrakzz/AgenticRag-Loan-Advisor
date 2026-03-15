param(
    [switch]$ForceReindex
)

Write-Host "== Qdrant + Policy Index Bootstrap ==" -ForegroundColor Cyan

# 1. Ensure Docker is available
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker is not installed or not on PATH. Install Docker Desktop first." -ForegroundColor Red
    exit 1
}

$containerName = "rag-qdrant"
$qdrantImage = "qdrant/qdrant:latest"
$portHTTP = 6333
$portGRPC = 6334

# 2. Start (or run) container
$existing = docker ps -a --filter "name=$containerName" --format '{{.ID}}'
if ($existing) {
    $running = docker ps --filter "name=$containerName" --format '{{.ID}}'
    if (-not $running) {
        Write-Host "Starting existing Qdrant container..." -ForegroundColor Yellow
        docker start $containerName | Out-Null
    } else {
        Write-Host "Qdrant container already running." -ForegroundColor Green
    }
} else {
    Write-Host "Launching new Qdrant container..." -ForegroundColor Yellow
    docker run -d --name $containerName -p $portHTTP:6333 -p $portGRPC:6334 $qdrantImage | Out-Null
}

# 3. Wait for readiness
Write-Host "Waiting for Qdrant to become ready on http://localhost:$portHTTP ..." -ForegroundColor Cyan
$maxWait = 30
$ready = $false
for ($i=0; $i -lt $maxWait; $i++) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$portHTTP/collections" -TimeoutSec 2
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
    Write-Host "ERROR: Qdrant did not become ready in $maxWait seconds." -ForegroundColor Red
    exit 1
}
Write-Host "Qdrant is ready." -ForegroundColor Green

# 4. (Re)index policy chunks
$reindexFlag = ""
if ($ForceReindex) { $reindexFlag = "--reindex" }

Write-Host "Indexing policy chunks..." -ForegroundColor Cyan
$python = "python"  # Adjust if a specific venv/python is required
$indexCmd = "$python -m app.rag.index_policy $reindexFlag"
Write-Host $indexCmd -ForegroundColor DarkGray
Invoke-Expression $indexCmd
if ($LASTEXITCODE -ne 0) { Write-Host "Indexing failed." -ForegroundColor Red; exit 1 }

# 5. Verify setup
Write-Host "Verifying RAG setup..." -ForegroundColor Cyan
$verifyCmd = "$python scripts/verify_rag_setup.py"
Write-Host $verifyCmd -ForegroundColor DarkGray
Invoke-Expression $verifyCmd
if ($LASTEXITCODE -ne 0) { Write-Host "Verification failed." -ForegroundColor Red; exit 1 }

Write-Host "All done. You can now ask policy questions in the UI." -ForegroundColor Green
