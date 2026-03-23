param(
    [int]$StartPort = 8502,
    [int]$MaxPort = 8510,
    [string]$Address = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$pythonCandidates = @(
    (Join-Path $PSScriptRoot ".venv-5\Scripts\python.exe")
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
    "python"
)

$pythonExe = $null
foreach ($c in $pythonCandidates) {
    if ($c -eq "python") {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $pythonExe = "python"; break }
    } elseif (Test-Path $c) {
        $pythonExe = $c
        break
    }
}

if (-not $pythonExe) {
    throw "Could not find Python. Expected .venv-5, .venv, or system python."
}

# Ensure venv Scripts is first on PATH so Streamlit child processes don't fall back to WindowsApps Python.
$venvScripts = @(
    (Join-Path $PSScriptRoot ".venv-5\Scripts")
    (Join-Path $PSScriptRoot ".venv\Scripts")
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($venvScripts) {
    $env:PATH = "$venvScripts;$env:PATH"
}

function Test-PortFree([int]$port) {
    $inUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    return ($null -eq $inUse)
}

$port = $null
for ($p = $StartPort; $p -le $MaxPort; $p++) {
    if (Test-PortFree $p) { $port = $p; break }
}

if (-not $port) {
    throw "No free port found in range $StartPort..$MaxPort"
}

Write-Host "Starting Streamlit on http://$Address`:$port" -ForegroundColor Cyan

$streamlitExe = if ($venvScripts) { Join-Path $venvScripts "streamlit.exe" } else { $null }

if ($streamlitExe -and (Test-Path $streamlitExe)) {
    & $streamlitExe run "ui\streamlit_app.py" --server.address $Address --server.port $port --server.headless true --server.fileWatcherType none --server.enableCORS false --server.enableXsrfProtection false --server.enableWebsocketCompression false
} else {
    & $pythonExe -m streamlit run "ui\streamlit_app.py" --server.address $Address --server.port $port --server.headless true --server.fileWatcherType none --server.enableCORS false --server.enableXsrfProtection false --server.enableWebsocketCompression false
}
