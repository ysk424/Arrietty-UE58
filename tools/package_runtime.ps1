[CmdletBinding()]
param([string]$EngineRoot='C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$project=Join-Path $repo 'unreal\ArriettyUE\ArriettyUE.uproject'
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'logs') | Out-Null
& (Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat') ArriettyUEEditor Win64 Development "-Project=$project" -WaitMutex -NoHotReloadFromIDE *> (Join-Path $repo 'logs\runtime-editor-build.log')
if ($LASTEXITCODE -ne 0) { throw 'Editor build failed; see logs/runtime-editor-build.log' }
$contentLog=Join-Path $repo 'logs\runtime-content.log'
$contentScript=Join-Path $PSScriptRoot 'build_runtime_content.py'
& (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') $project -unattended -nop4 -nosplash -nosound -nohmd -NullRHI -run=pythonscript "-script=$contentScript" "-abslog=$contentLog" *> (Join-Path $repo 'logs\runtime-content-console.log')
if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath $contentLog -Pattern 'ARRIETTY_RUNTIME_CONTENT_READY' -Quiet)) { throw 'Runtime content generation failed' }
$output=Join-Path $repo 'build\runtime'
& (Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat') BuildCookRun "-project=$project" -noP4 -platform=Win64 -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$output" '-map=/Game/Maps/ArriettyEntry' -utf8output -unattended *> (Join-Path $repo 'logs\runtime-package.log')
if ($LASTEXITCODE -ne 0) { throw 'Runtime packaging failed; see logs/runtime-package.log' }
& py -3.13 (Join-Path $PSScriptRoot 'runtime_receipt.py') (Join-Path $output 'Windows') --engine $EngineRoot
if ($LASTEXITCODE -ne 0) { throw 'Runtime receipt failed' }
Write-Output "Packaged runtime: $output\Windows"
