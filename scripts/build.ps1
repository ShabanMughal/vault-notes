# Builds dist\VaultNotes.exe (run from anywhere).
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name VaultNotes --icon "$root\assets\icon.ico" --paths "$root\src" `
    --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
    "$root\src\vault_notes\__main__.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built: $root\dist\VaultNotes.exe"
