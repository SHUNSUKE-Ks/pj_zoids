# Blenderをヘッドレスで実行するラッパー
# 使い方: .\tools\bl.ps1 src\build_field.py [-- スクリプトへの引数]
#         .\tools\bl.ps1 -Blend out\field.blend src\render_preview.py
param(
  [string]$Blend,
  [Parameter(Mandatory=$true, Position=0)][string]$Script,
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)
$blender = $env:BLENDER_EXE
if (-not $blender) { $blender = "C:\Program Files\Blender Foundation\Blender 4.4\blender.exe" }
$root = Split-Path $PSScriptRoot -Parent
$argsList = @("-b", "--factory-startup")
if ($Blend) { $argsList += (Join-Path $root $Blend) }
$src = (Join-Path $root "src") -replace "\\", "/"
$argsList += @("--python-expr", "import sys; sys.path.insert(0, '$src')")
$argsList += @("--python", (Join-Path $root $Script), "--python-exit-code", "1")
if ($Rest) { $argsList += "--"; $argsList += $Rest }
Push-Location $root
& $blender @argsList
$code = $LASTEXITCODE
Pop-Location
exit $code
