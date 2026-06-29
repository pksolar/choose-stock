try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 5
    Write-Host "Backend: $($r.Content)"
} catch {
    Write-Host "Backend DOWN: $_"
}

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 5
    Write-Host "Frontend: $($r.StatusCode)"
} catch {
    Write-Host "Frontend DOWN"
}
