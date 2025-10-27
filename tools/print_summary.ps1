# tools/print_summary.ps1
# Print quad-scrape summary as Markdown + conclusion line (PS 5.1+ compatible)

$ErrorActionPreference = "Stop"

function Safe([object]$v) {
  if ($null -eq $v) { return "n/a" }
  return $v
}

$normDir = "tmp_norm"
$chunkDir = "tmp_chunks"
$embDir = "tmp_emb_local"
$linkDir = "step_D_tests\linked_runA"

# Counts
$normCount  = (Get-ChildItem -File $normDir -EA SilentlyContinue | Measure-Object).Count
$chunkCount = (Get-ChildItem -File $chunkDir -Filter *.jsonl -EA SilentlyContinue | Measure-Object).Count
$embCount   = (Get-ChildItem -File $embDir -Filter *.embedded.jsonl -Recurse -EA SilentlyContinue | Measure-Object).Count
$linkCount  = (Get-ChildItem -File $linkDir -Filter linked*.jsonl -EA SilentlyContinue | Measure-Object).Count

# Reports
$embedRepPath = Join-Path $embDir "_reports\run_report.json"
$linkRepPath  = Join-Path $linkDir "_reports\run_report.json"

$embedRep = $null
if (Test-Path $embedRepPath) {
  $embedRep = Get-Content $embedRepPath -Raw | ConvertFrom-Json
}

$linkRep = $null
if (Test-Path $linkRepPath) {
  $linkRep = Get-Content $linkRepPath -Raw | ConvertFrom-Json
}

# Extract fields safely
$embedErrors = $null
if ($embedRep) { $embedErrors = $embedRep.errors }
$embedErrors = Safe($embedErrors)

$embedWritten = $null
if ($embedRep) { $embedWritten = $embedRep.written }
$embedWritten = Safe($embedWritten)

# adapter may live at top-level or under meta.adapter
$adapter = $null
if ($embedRep -and $embedRep.PSObject.Properties.Name -contains "adapter" -and $embedRep.adapter) {
  $adapter = $embedRep.adapter
} elseif ($embedRep -and $embedRep.meta -and $embedRep.meta.adapter) {
  $adapter = $embedRep.meta.adapter
}
$adapter = Safe($adapter)

# notes may be array or string
$notes = $null
if ($embedRep -and $embedRep.notes) {
  if ($embedRep.notes -is [System.Array]) { $notes = ($embedRep.notes -join "; ") } else { $notes = [string]$embedRep.notes }
}
$notes = Safe($notes)

$linkDocs = $null
if ($linkRep) { $linkDocs = $linkRep.docs }
$linkDocs = Safe($linkDocs)

$linkEntities = $null
if ($linkRep) { $linkEntities = $linkRep.entities }
$linkEntities = Safe($linkEntities)

$linkErrors = $null
if ($linkRep) { $linkErrors = $linkRep.errors }
$linkErrors = Safe($linkErrors)

# Compute status conservatively
function ToIntOrZero($x) {
  if ($x -eq $null -or $x -eq "n/a") { return 0 }
  [int]$x
}

$embedErrInt = if ($embedRep) { ToIntOrZero $embedRep.errors } else { 0 }
$linkErrInt  = if ($linkRep)  { ToIntOrZero $linkRep.errors }  else { 0 }
$entInt      = if ($linkRep)  { ToIntOrZero $linkRep.entities } else { 0 }

$status = if (($embedErrInt -eq 0) -and ($linkErrInt -eq 0) -and ($entInt -gt 0)) { "SUCCESS" } else { "CHECK" }

# Derive adapter if missing but notes include force_local
if ($adapter -eq "n/a") {
  if (($notes -is [string]) -and ($notes -match "force_local")) {
    $adapter = "local"
  }
}

# Markdown table
Write-Output "| Metric            | Value |"
Write-Output "| ----------------- | ----: |"
Write-Output ("| Normalized files  | {0} |" -f $normCount)
Write-Output ("| Chunk files       | {0} |" -f $chunkCount)
Write-Output ("| Embedded files    | {0} |" -f $embCount)
Write-Output ("| Linked files      | {0} |" -f $linkCount)
Write-Output ("| Embed written     | {0} |" -f $embedWritten)
Write-Output ("| Embed errors      | {0} |" -f $embedErrors)
Write-Output ("| Link docs         | {0} |" -f $linkDocs)
Write-Output ("| Link entities     | {0} |" -f $linkEntities)
Write-Output ("| Adapter           | {0} |" -f $adapter)
Write-Output ("| Notes             | {0} |" -f $notes)
Write-Output ("| Status            | {0} |" -f $status)

# Conclusion line (explicit variable to avoid truncation)
$cline = "Status: {0} — Normalized={1} | Chunks={2} | Embedded={3} (written={4}, adapter={5}, notes={6}) | Linking: docs={7}, entities={8}" -f `
  $status, $normCount, $chunkCount, $embCount, $embedWritten, $adapter, $notes, $linkDocs, $linkEntities
Write-Output $cline
