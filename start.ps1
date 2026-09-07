# Typed forwarding preserves switches and paths under PowerShell 5.1 and 7.
[CmdletBinding()]
param(
    [switch]$Offline, [switch]$SmokeTest, [switch]$Headless,
    [string]$LocalDate, [string]$LocalTime, [string]$WorldRoot,
    [string]$WorldManifest, [string]$RuntimeRoot,
    [int]$WorldPort, [int]$Port, [string]$EngineRoot
)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'start-ue.ps1') @PSBoundParameters
