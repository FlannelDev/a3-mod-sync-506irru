$ErrorActionPreference="Stop"
$Root=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
py -m pip install -r requirements-build.txt
Remove-Item -Recurse -Force build,dist -ErrorAction SilentlyContinue
py -m PyInstaller --noconfirm --clean --onedir --windowed --name "506th-Arma3-Mod-Sync" "src\506th_mod_sync.py"
$Version="5.0.0"
New-Item -ItemType Directory -Force release | Out-Null
$Zip="release\506th-Arma3-Mod-Sync-v$Version-Windows-x64.zip"
Remove-Item $Zip -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\506th-Arma3-Mod-Sync\*" -DestinationPath $Zip -CompressionLevel Optimal
$Hash=(Get-FileHash $Zip -Algorithm SHA256).Hash
"$Hash  506th-Arma3-Mod-Sync-v$Version-Windows-x64.zip" | Set-Content "release\SHA256SUMS.txt"
Write-Host "Built $Zip" -ForegroundColor Green
