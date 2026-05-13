param(
    [switch]$SkipTests,
    [string]$InnoSetupCompiler = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Version = "3.0.0"
$Spec = Join-Path $Root "build\roco_navigator.spec"
$DistDir = Join-Path $Root "dist"
$AppDist = Join-Path $DistDir "RocoNavigator"
$InstallerScript = Join-Path $Root "installer\roco_navigator.iss"
$ReleaseDir = Join-Path $Root "release"
$PortableZip = Join-Path $ReleaseDir "RocoNavigator-$Version-Portable.zip"

Set-Location $Root

Write-Host "== Roco Navigator $Version release build =="

if (-not $SkipTests) {
    Write-Host "== Running compileall =="
    python -m compileall main.py config core data ui utils vision tests

    Write-Host "== Running unit tests =="
    python -m unittest discover -s tests -v
}

Write-Host "== Ensuring build dependencies =="
python -m pip install --upgrade pip pyinstaller setuptools wheel

Write-Host "== Cleaning previous build output =="
if (Test-Path $AppDist) {
    Remove-Item -LiteralPath $AppDist -Recurse -Force
}

Write-Host "== Building PyInstaller distribution =="
python -m PyInstaller --clean --noconfirm $Spec

if (-not (Test-Path (Join-Path $AppDist "RocoNavigator.exe"))) {
    throw "PyInstaller did not produce dist\RocoNavigator\RocoNavigator.exe"
}

Write-Host "== Building portable zip =="
if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
}
if (Test-Path $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Compress-Archive -Path (Join-Path $AppDist "*") -DestinationPath $PortableZip -Force

if (-not $InnoSetupCompiler) {
    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            $InnoSetupCompiler = $Candidate
            break
        }
    }
}

if ($InnoSetupCompiler -and (Test-Path $InnoSetupCompiler)) {
    Write-Host "== Building installer =="
    & $InnoSetupCompiler $InstallerScript
} else {
    Write-Warning "Inno Setup compiler not found. Install Inno Setup 6 or pass -InnoSetupCompiler to build the installer."
}

Write-Host "== Done =="
Write-Host "App distribution: $AppDist"
Write-Host "Portable zip: $PortableZip"
Write-Host "Installer output: $(Join-Path $Root 'installer\output')"
