param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
  # Prefer an activated venv if present
  $venvCandidates = @(
    (Join-Path $ProjectRoot "venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
  )
  foreach ($p in $venvCandidates) {
    if (Test-Path $p) { return $p }
  }

  # Try common launchers/commands (may be Microsoft Store aliases, we filter those out below)
  foreach ($name in @("py", "python", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
      # Filter out Microsoft Store alias shims
      if ($cmd.Source -like "*\Microsoft\WindowsApps\python*.exe") { continue }
      return $cmd.Source
    }
  }

  # Try typical install locations
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe"
  )
  foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { return $p }
  }

  return $null
}

$python = Resolve-Python
if (-not $python) {
  Write-Error "No real Python interpreter found. Install Python (3.9+) or create a venv in the repo (venv/.venv)."
}

Write-Host ("Using Python: {0}" -f $python)
& $python --version
Push-Location $ProjectRoot
try {
  & $python -m compileall -q .
  Write-Host "compileall OK"
} finally {
  Pop-Location
}

