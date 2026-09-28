# Install / update xingce skills into the Obsidian Copilot skills folder (Windows).
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/dingzhen164-coder/obsidian-to-xingce/refs/heads/claude/continue-previous-conversation-8zt03d/install.ps1 | iex
# Optional: set $SK = "<skills folder>" before running to skip auto-detection.
# ASCII only on purpose: Windows PowerShell 5.1 misreads non-ASCII in scripts.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$Branch = "claude/continue-previous-conversation-8zt03d"
$Zip = "https://github.com/dingzhen164-coder/obsidian-to-xingce/archive/refs/heads/$Branch.zip"
$BoardSkills = "political-theory-reasoning","center-comprehension-jiangwei","xue-rui-argument-logic","xue-rui-formal-logic","xue-rui-yituowu"

# 1) find the skills folder (the one containing xue-rui-formal-logic)
if (-not $SK) {
  $hit = Get-ChildItem "$env:USERPROFILE\Desktop","$env:USERPROFILE\Documents" -Recurse -Directory -Depth 6 `
           -Filter "xue-rui-formal-logic" -ErrorAction SilentlyContinue |
         Where-Object { $_.FullName -notmatch '\.old' } | Select-Object -First 1
  if (-not $hit) { throw "skills folder not found. Run:  `$SK = '<your skills folder>'  first, then rerun." }
  $SK = $hit.Parent.FullName
}
Write-Host "[1/5] skills folder: $SK"

# 2) download
$tmp = Join-Path $env:TEMP "xingce-skills"
Remove-Item $tmp, "$tmp.zip" -Recurse -Force -ErrorAction SilentlyContinue
Invoke-WebRequest $Zip -OutFile "$tmp.zip" -UseBasicParsing
Expand-Archive "$tmp.zip" $tmp -Force
$src = Join-Path (Get-ChildItem $tmp -Directory)[0].FullName "skills"
Write-Host "[2/5] downloaded"

# 3) rename center-comprehension folder so it matches its name: field
$old = Join-Path $SK "center-comprehension-booktoskill"
$new = Join-Path $SK "center-comprehension-jiangwei"
if ((Test-Path $old) -and -not (Test-Path $new)) { Rename-Item $old "center-comprehension-jiangwei" }
Write-Host "[3/5] center-comprehension folder ok: $(Test-Path $new)"

# 4) replace the 5 board SKILL.md (original kept once as SKILL.md.bak)
foreach ($s in $BoardSkills) {
  $d = Join-Path $SK $s
  if (-not (Test-Path $d)) { Write-Host "      skip $s (folder missing)"; continue }
  if (-not (Test-Path "$d\SKILL.md.bak")) { Copy-Item "$d\SKILL.md" "$d\SKILL.md.bak" }
  Copy-Item "$src\$s\SKILL.md" "$d\SKILL.md" -Force
  Write-Host "      updated $s"
}
Write-Host "[4/5] board skills updated"

# 5) install / update our own skills (copy contents, never nest folders)
foreach ($s in "xingce-jiexi-all","xingce-mokao-split") {
  $d = Join-Path $SK $s
  New-Item $d -ItemType Directory -Force | Out-Null
  Copy-Item "$src\$s\*" $d -Recurse -Force
  Write-Host "      installed $s : SKILL.md exists = $(Test-Path "$d\SKILL.md")"
}
Write-Host "[5/5] done. Python check:"
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { $null }
if ($py) { & $py (Join-Path $SK "xingce-jiexi-all\scripts\jiexi.py") -h | Select-Object -First 1 }
else { Write-Host "      Python not found - install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')" }
