<#
.SYNOPSIS
UE 5.8 Arriettyを起動。Pで実機準備、Button 1で照準・走行開始、Escで準備画面。
.EXAMPLE
.\start-ue.ps1 -Offline
.EXAMPLE
.\start-ue.ps1 -LocalDate 2026-09-07 -LocalTime 17:45
#>
[CmdletBinding()]
param(
    [switch]$Offline,
    [switch]$SmokeTest,
    [switch]$Headless,
    [string]$LocalDate = '',
    [string]$LocalTime = '17:45',
    [string]$WorldRoot = '',
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8'
)
$ErrorActionPreference='Stop'
$repo=$PSScriptRoot
if (-not $WorldRoot) { $WorldRoot=Join-Path (Split-Path -Parent $repo) 'Secret-World' }
$project=Join-Path $repo 'unreal\ArriettyUE\ArriettyUE.uproject'
$editor=Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
if (($SmokeTest -or $Headless) -and -not $Offline) { throw 'SmokeTest/Headless requires -Offline.' }
if (-not (Test-Path (Join-Path $repo 'unreal\ArriettyUE\Content\Maps\Funafuti.umap'))) { throw 'Run .\tools\prepare_ue.ps1 first.' }
if (Get-NetUDPEndpoint -LocalPort 19858 -ErrorAction SilentlyContinue) { throw 'An Arrietty UE bridge is already running (UDP 19858).' }
if (-not $Offline) {
    if (Get-Process blender -ErrorAction SilentlyContinue) { throw 'Close the UPBGE/Blender simulator before live UE use to avoid competing device ownership.' }
    if (-not (Get-Process vrserver -ErrorAction SilentlyContinue)) { throw 'Start SteamVR before launching live UE.' }
}
$version=Get-Content (Join-Path $EngineRoot 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
if ($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8) { throw 'UE 5.8 is required.' }
$python=(& py -3.13 -c 'import sys; print(sys.executable)').Trim()
if (-not (Test-Path (Join-Path $repo '.runtime\current.txt'))) { & $python (Join-Path $repo 'tools\install_runtime_dependencies.py') }
$sessionArgs=@((Join-Path $repo 'tools\ue_session.py'),'--time',$LocalTime,'--world-root',$WorldRoot)
# Windows PowerShell 5.1 drops empty native-command arguments. Omit the
# optional date so Python selects today's Tuvalu date with its own default.
if ($LocalDate) { $sessionArgs+=@('--date',$LocalDate) }
if (-not $Offline) { $sessionArgs+='--hardware' }
& $python @sessionArgs
if ($LASTEXITCODE -ne 0) { throw 'UE session preparation failed.' }
$session=Join-Path $repo '.runtime\ue\session.json'
$solar=Join-Path $repo '.runtime\ue\world-session.json'
$envBeforeSession=$env:ARRIETTY_UE_SESSION
$envBeforeSolar=$env:ARRIETTY_UE_SOLAR
$bridge=$null
try {
    $env:ARRIETTY_UE_SESSION=$session
    $env:ARRIETTY_UE_SOLAR=$solar
    $bridgeArgs=@('-u',('"'+(Join-Path $repo 'tools\ue_bridge.py')+'"'),'--world',('"'+$solar+'"'),'--session',('"'+$session+'"'))
    if (-not $Offline) { $bridgeArgs+='--hardware' }
    $bridge=Start-Process -FilePath $python -ArgumentList $bridgeArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $repo 'logs\latest-ue-bridge.log') -RedirectStandardError (Join-Path $repo 'logs\latest-ue-bridge.err.log')
    $deadline=[DateTime]::UtcNow.AddSeconds(8)
    do {
        Start-Sleep -Milliseconds 100
        if ($bridge.HasExited) { throw 'Bridge startup failed; see logs/latest-ue-bridge.err.log' }
        $ready=Select-String -LiteralPath (Join-Path $repo 'logs\latest-ue-bridge.log') -Pattern 'ARRIETTY_UE_BRIDGE_READY' -Quiet
    } until ($ready -or [DateTime]::UtcNow -gt $deadline)
    if (-not $ready) { throw 'Bridge startup timed out.' }
    $ueArgs=@(('"'+$project+'"'),'-game','-nosplash','-nop4',('-abslog="'+(Join-Path $repo 'logs\latest-ue.log')+'"'),'-windowed','-ResX=1600','-ResY=900')
    if ($Offline) { $ueArgs+='-nohmd' } else { $ueArgs+='-vr' }
    if ($SmokeTest) { $ueArgs+='-ArriettySmoke'; $ueArgs+='-unattended' }
    if ($Headless) { $ueArgs+='-RenderOffscreen'; $ueArgs+='-nosound' }
    if ($Headless) { $app=Start-Process -FilePath $editor -ArgumentList $ueArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru }
    else { $app=Start-Process -FilePath $editor -ArgumentList $ueArgs -WorkingDirectory $repo -PassThru }
    $app.WaitForExit()
    if ($app.ExitCode -ne 0) { throw "Unreal exited with code $($app.ExitCode). See logs/latest-ue.log" }
    if ($SmokeTest -and -not (Select-String -LiteralPath (Join-Path $repo 'logs\latest-ue.log') -Pattern 'ARRIETTY_UE_SMOKE_DONE' -Quiet)) { throw 'UE smoke test did not complete.' }
} finally {
    if ($bridge -and -not $bridge.HasExited) {
        # The engine normally sends quit. Crash cleanup first uses the existing
        # loopback watchdog so the workers can release brake/PTT/fan normally.
        if (-not $bridge.WaitForExit(35000)) { Stop-Process -Id $bridge.Id }
    }
    $env:ARRIETTY_UE_SESSION=$envBeforeSession
    $env:ARRIETTY_UE_SOLAR=$envBeforeSolar
}
