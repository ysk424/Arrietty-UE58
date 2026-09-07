[CmdletBinding()]
param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string]$WorldRoot = '',
    [string]$BlenderPath = '',
    [switch]$SkipExport,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Join-Path $repo 'unreal\ArriettyUE\ArriettyUE.uproject'
if (-not $WorldRoot) { $WorldRoot = Join-Path (Split-Path -Parent $repo) 'Secret-World' }
$version = Get-Content -LiteralPath (Join-Path $EngineRoot 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
if ($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8) { throw 'UE 5.8 is required.' }
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'logs') | Out-Null
if (-not $SkipExport) {
    $blender = if ($BlenderPath) { $BlenderPath } else { Join-Path (Split-Path -Parent $repo) 'build_upbge_windows_Release_x64_vc17_Release\bin\blender.exe' }
    & $blender --background --factory-startup --python-exit-code 2 --python (Join-Path $PSScriptRoot 'export_secret_world_ue.py') -- --source-root $WorldRoot *> (Join-Path $repo 'logs\ue-export.log')
    if ($LASTEXITCODE -ne 0) { throw 'World export failed; see logs/ue-export.log' }
}
if (-not $SkipBuild) {
    & (Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat') ArriettyUEEditor Win64 Development "-Project=$project" -WaitMutex -NoHotReloadFromIDE *> (Join-Path $repo 'logs\ue-build.log')
    if ($LASTEXITCODE -ne 0) { throw 'UE build failed; see logs/ue-build.log' }
}
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$contentScript = Join-Path $PSScriptRoot 'build_ue_content.py'
$contentLog = Join-Path $repo 'logs\ue-content.log'
& $editor $project -unattended -nop4 -nosplash -nosound -nohmd -NullRHI -run=pythonscript "-script=$contentScript" "-abslog=$contentLog" *> (Join-Path $repo 'logs\ue-content-console.log')
if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath $contentLog -Pattern 'ARRIETTY_UE_CONTENT_READY' -Quiet)) { throw 'UE content preparation failed; see logs/ue-content.log' }
Write-Output "Ready: $project"
