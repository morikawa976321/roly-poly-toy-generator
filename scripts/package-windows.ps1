$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$appName = "roly-poly-toy-generator"
$releaseRoot = Join-Path $repoRoot "build\release"
$zipPath = Join-Path $releaseRoot "$appName-windows.zip"
$stagingRoot = Join-Path $repoRoot ("build\package-staging\" + [guid]::NewGuid().ToString("N"))
$releaseDir = Join-Path $stagingRoot $appName
$pyinstallerDir = Join-Path $repoRoot "build\pyinstaller-dist\$appName"
$frontendDist = Join-Path $repoRoot "frontend\dist"

Push-Location $repoRoot
try {
  npm run build:frontend
  npm run build:exe

  New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
  New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

  Copy-Item (Join-Path $pyinstallerDir "*") $releaseDir -Recurse -Force

  $frontendOut = Join-Path $releaseDir "frontend\dist"
  New-Item -ItemType Directory -Force -Path $frontendOut | Out-Null
  Copy-Item (Join-Path $frontendDist "*") $frontendOut -Recurse -Force

  New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir "data") | Out-Null

  if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
  }
  Compress-Archive -Path $releaseDir -DestinationPath $zipPath
  Write-Host "Created $zipPath"
}
finally {
  if (Test-Path $stagingRoot) {
    Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
  Pop-Location
}
