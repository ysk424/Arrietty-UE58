[CmdletBinding()]
param([string]$EngineRoot='C:\Program Files\Epic Games\UE_5.8',[switch]$Smoke)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    & py -3.13 -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed' }
    & py -3.13 .\tools\verify_ue_world.py
    if ($LASTEXITCODE -ne 0) { throw 'World validation failed' }
    $log=Join-Path $repo 'logs\ue-automation.log'
    & (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') (Join-Path $repo 'unreal\ArriettyUE\ArriettyUE.uproject') -unattended -nop4 -nosound -nohmd -NullRHI '-ExecCmds=Automation RunTests Arrietty.' '-TestExit=Automation Test Queue Empty' "-abslog=$log" *> (Join-Path $repo 'logs\ue-automation-console.log')
    if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath $log -Pattern 'Result=\{Success\}.*Arrietty.Coordinates.Attitude' -Quiet)) { throw 'Native UE tests failed; see logs/ue-automation.log' }
    if ($Smoke) { & .\start-ue.ps1 -Offline -SmokeTest -Headless -EngineRoot $EngineRoot }
} finally { Pop-Location }
