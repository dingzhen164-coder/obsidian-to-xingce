# Install / update xingce skills (Windows). Updates both copilot\skills and .opencode\skills
# in the vault (opencode actually reads .opencode\skills).
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/dingzhen164-coder/obsidian-to-xingce/refs/heads/claude/continue-previous-conversation-8zt03d/install.ps1 | iex
# Optional: set $SK = "<copilot\skills folder>" before running to skip auto-detection.
# ASCII only on purpose: Windows PowerShell 5.1 misreads non-ASCII in scripts.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$Branch = "claude/continue-previous-conversation-8zt03d"
$Zip = "https://github.com/dingzhen164-coder/obsidian-to-xingce/archive/refs/heads/$Branch.zip"
$BoardSkills = "political-theory-reasoning","center-comprehension-jiangwei","xue-rui-argument-logic","xue-rui-formal-logic","xue-rui-yituowu"

# 1) find the vault root (two levels above copilot\skills or .opencode\skills)
if (-not $SK) {
  $hits = Get-ChildItem "$env:USERPROFILE\Desktop","$env:USERPROFILE\Documents" -Recurse -Directory -Depth 6 -Force `
            -Filter "xue-rui-formal-logic" -ErrorAction SilentlyContinue |
          Where-Object { $_.FullName -notmatch '\.old' }
  $hit = ($hits | Where-Object { $_.FullName -match '\\copilot\\skills\\' } | Select-Object -First 1)
  if (-not $hit) { $hit = $hits | Select-Object -First 1 }
  if (-not $hit) { throw "skills folder not found. Run:  `$SK = '<your copilot\skills folder>'  first, then rerun." }
  $SK = $hit.Parent.FullName
}
$Vault = Split-Path (Split-Path $SK -Parent) -Parent
$Targets = @(@((Join-Path $Vault "copilot\skills"), (Join-Path $Vault ".opencode\skills")) | Where-Object { Test-Path $_ })
Write-Host "[1/5] vault: $Vault"
foreach ($t in $Targets) { Write-Host "      will update: $t" }

# 2) download
$tmp = Join-Path $env:TEMP "xingce-skills"
Remove-Item $tmp, "$tmp.zip" -Recurse -Force -ErrorAction SilentlyContinue
Invoke-WebRequest $Zip -OutFile "$tmp.zip" -UseBasicParsing
Expand-Archive "$tmp.zip" $tmp -Force
$src = Join-Path (Get-ChildItem $tmp -Directory)[0].FullName "skills"
Write-Host "[2/5] downloaded"
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { $null }
if (-not $py) { throw "Python not found - install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')" }
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# skill doctor: folder name != name:, duplicate folders of one skill, stale/missing files in .opencode\skills -- fixes ALL skills
$Doctor = Join-Path $src "xingce-jiexi-all\scripts\skills_doctor.py"
Write-Host "== skill doctor (before update)"
& $py $Doctor $Vault --fix

foreach ($T in $Targets) {
  Write-Host "== $T"
  $new = Join-Path $T "center-comprehension-jiangwei"
  $nch = @(Get-ChildItem (Join-Path $new "chapters") -File -ErrorAction SilentlyContinue).Count
  Write-Host "[3/5] center-comprehension folder ok: $(Test-Path $new) ; chapter files: $nch"

  # 4) replace the 5 board SKILL.md (original kept once as SKILL.md.bak)
  foreach ($s in $BoardSkills) {
    $d = Join-Path $T $s
    if (-not (Test-Path $d)) { Write-Host "      skip $s (folder missing)"; continue }
    if (-not (Test-Path "$d\SKILL.md.bak")) { Copy-Item "$d\SKILL.md" "$d\SKILL.md.bak" }
    Copy-Item "$src\$s\SKILL.md" "$d\SKILL.md" -Force
    Write-Host "      updated $s"
  }
  Write-Host "[4/5] board skills updated"

  # 5) install / update our own skills (copy contents, never nest folders)
  # remove old non-ASCII-named files of earlier versions (now board-map.md / board-skill-template.md)
  $jd = Join-Path $T "xingce-jiexi-all"
  if (Test-Path $jd) {
    Get-ChildItem $jd -Filter *.md | Where-Object { $_.Name -notmatch '^(SKILL|board-[a-z-]+)\.md$' } | Remove-Item -Force
  }
  foreach ($s in "xingce-jiexi-all","xingce-mokao-split","xingce-changshi","xingce-shuliang","xingce-feiman") {
    $d = Join-Path $T $s
    New-Item $d -ItemType Directory -Force | Out-Null
    Copy-Item "$src\$s\*" $d -Recurse -Force
    Write-Host "      installed $s : SKILL.md exists = $(Test-Path "$d\SKILL.md")"
  }
  # patch book-to-skill with the xingce mode section (original kept as SKILL.md.bak)
  $b2s = Join-Path $T "book-to-skill"
  if (Test-Path "$b2s\SKILL.md") {
    & $py (Join-Path $T "xingce-jiexi-all\scripts\patch_book_to_skill.py") $b2s
  }
}

# run the doctor again: sync the freshly updated copilot\skills into .opencode\skills
Write-Host "== skill doctor (sync .opencode)"
& $py $Doctor $Vault --fix

Write-Host "[5/5] done. Check:"
& $py (Join-Path $Targets[0] "xingce-jiexi-all\scripts\jiexi.py") -h | Select-Object -First 1
foreach ($T in $Targets) {
  $n = 0
  foreach ($s in $BoardSkills) {
    $f = Join-Path $T "$s\SKILL.md"
    if ((Test-Path $f) -and (Select-String -Path $f -Pattern "xingce-jiexi-all" -SimpleMatch -Quiet)) { $n++ }
  }
  Write-Host "      $T : $n of 5 board skills have the dispatch section"
}
