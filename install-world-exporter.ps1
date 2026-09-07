# Close the source project's UE Editor before running this installer.
# Example: .\install-world-exporter.ps1 newWorld
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectName
)
$ErrorActionPreference='Stop'
if ([string]::IsNullOrWhiteSpace($ProjectName) -or
    $ProjectName -in @('.', '..') -or
    $ProjectName.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
    throw 'Specify only the project folder name, for example: newWorld'
}
$projectsRoot=Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Documents\Unreal Projects'
$projectDirectory=Join-Path $projectsRoot $ProjectName
if (-not (Test-Path -LiteralPath $projectDirectory -PathType Container)) {
    throw "Project folder not found: $projectDirectory"
}
$projects=@(Get-ChildItem -LiteralPath $projectDirectory -Filter '*.uproject' -File)
if ($projects.Count -ne 1) {
    throw "Expected exactly one .uproject in $projectDirectory; found $($projects.Count)."
}
$installer=Join-Path $PSScriptRoot 'tools\install_world_exporter.py'
Write-Output "Installing Arrietty Exporter into: $($projects[0].FullName)"
& py -3.13 $installer $projects[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'Arrietty Exporter installation failed.' }
