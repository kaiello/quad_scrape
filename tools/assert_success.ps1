# tools/assert_success.ps1
# Enforce SUCCESS gate for quad-scrape Steps A→D (PS 5.1+)
# Criteria: embed errors = 0, link errors = 0, link entities > 0

param(
  [switch]$RequireEmbedWritten  # fail if embed_written == 0
)

$ErrorActionPreference = "Stop"

function Fail($msg) {
  Write-Error $msg
  exit 1
}

function HasProp($obj, [string]$name) {
  return ($null -ne $obj) -and ($obj.PSObject.Properties.Name -contains $name)
}

function ToIntOrZero($x) {
  if ($x -eq $null) { return 0 }
  [int]$x
}

$embDir = "tmp_emb_local"
$linkDir = "step_D_tests\linked_runA"

$embedRepPath = Join-Path $embDir "_reports\run_report.json"
$linkRepPath  = Join-Path $linkDir "_reports\run_report.json"

if (-not (Test-Path $embedRepPath)) { Fail "Missing embed report: $embedRepPath" }
if (-not (Test-Path $linkRepPath))  { Fail "Missing link report:  $linkRepPath" }

$embedRep = Get-Content $embedRepPath -Raw | ConvertFrom-Json
$linkRep  = Get-Content $linkRepPath  -Raw | ConvertFrom-Json

if (-not (HasProp $embedRep 'errors')) { Fail "Embed report missing 'errors' field" }
if (-not (HasProp $linkRep  'errors')) { Fail "Link report missing 'errors' field" }
if (-not (HasProp $linkRep  'entities')) { Fail "Link report missing 'entities' field" }

$embedErrorsInt = ToIntOrZero $embedRep.errors
$linkErrorsInt  = ToIntOrZero $linkRep.errors
$entitiesInt    = ToIntOrZero $linkRep.entities

# Optional strict check for embed_written
$embedWrittenInt = 0
if (HasProp $embedRep 'written') { $embedWrittenInt = ToIntOrZero $embedRep.written }

$embedErrOK = ($embedErrorsInt -eq 0)
$linkErrOK  = ($linkErrorsInt  -eq 0)
$linkedOK   = ($entitiesInt    -gt 0)

$embedWrittenOK = $true
if ($RequireEmbedWritten.IsPresent) {
  $embedWrittenOK = ($embedWrittenInt -gt 0)
}

$allOK = $embedErrOK -and $linkErrOK -and $linkedOK -and $embedWrittenOK
$status = if ($allOK) { "SUCCESS" } else { "FAIL" }
$gateWord = if ($allOK) { "passed" } else { "failed" }

Write-Output (
  "ASSERT: {0} — gate {1} (embed_errors={2}, link_errors={3}, entities>0={4}, require_written={5}, written={6})" -f `
  $status, $gateWord, $embedErrOK, $linkErrOK, $linkedOK, $RequireEmbedWritten.IsPresent, $embedWrittenInt
)

if ($allOK) {
  exit 0
} else {
  exit 1
}
