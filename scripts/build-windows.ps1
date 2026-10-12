param(
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$TesseractPath,
    [string]$Python = "python",
    [string]$IsccPath = "",
    [switch]$SkipInstall
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Run this build on Windows x64."
}
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelPath = (Resolve-Path $ModelPath).Path
$TesseractPath = (Resolve-Path $TesseractPath).Path
if (-not (Test-Path "$TesseractPath\tesseract.exe")) { throw "TesseractPath must contain tesseract.exe and its DLLs." }
foreach ($Language in @("chi_sim", "chi_tra", "eng")) {
    if (-not (Test-Path "$TesseractPath\tessdata\$Language.traineddata")) { throw "Missing OCR language: $Language" }
}

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

Push-Location $RepoRoot
try {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Invoke-Checked $Python @("-m", "venv", ".venv")
    }
    $BuildPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not $SkipInstall) {
        Invoke-Checked $BuildPython @("-m", "pip", "install", "--require-hashes", "-r", "requirements.lock")
        Invoke-Checked $BuildPython @("-m", "pip", "install", "--index-url", "https://download.pytorch.org/whl/cpu", "torch==2.5.1")
        Invoke-Checked $BuildPython @("-m", "pip", "install", "-e", ".[offline,build]")
    }
    # Install the user's accepted local Argos package. No model download or benchmark.
    $BundleModels = Join-Path $RepoRoot "build\argos-packages"
    New-Item -ItemType Directory -Force $BundleModels | Out-Null
    $env:ARGOS_PACKAGES_DIR = $BundleModels
    $env:ARGOS_DEVICE_TYPE = "cpu"
    Invoke-Checked $BuildPython @("-c", "import sys; from argostranslate import package; package.install_from_path(sys.argv[1])", $ModelPath)
    Invoke-Checked $BuildPython @("-c", "from pathlib import Path; from converter.config import ProviderConfig; ProviderConfig.load(Path('config/provider.json')).validate()")
    $env:CONVERTER_BUNDLE_OFFLINE = "1"
    $env:CONVERTER_BUNDLE_MODELS = $BundleModels
    $env:CONVERTER_BUNDLE_TESSERACT = $TesseractPath
    Invoke-Checked $BuildPython @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/converter.spec")
    Invoke-Checked $BuildPython @("scripts/collect-notices.py", "dist/Converter/THIRD_PARTY_NOTICES.txt")
    Invoke-Checked $BuildPython @("scripts/check-size.py", "dist/Converter")
    if (-not $IsccPath) {
        $IsccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($IsccCommand) { $IsccPath = $IsccCommand.Source }
    }
    if ($IsccPath) {
        Invoke-Checked $IsccPath @("packaging/installer.iss")
        Invoke-Checked $BuildPython @("scripts/check-size.py", "dist/Converter-Setup-0.1.0.exe")
    } else {
        Write-Host "Portable build: dist\Converter. Install Inno Setup 6 and run ISCC packaging\installer.iss to create the installer."
    }
} finally {
    Pop-Location
}
