param([string]$RecordPath = (Join-Path $PSScriptRoot 'rehearsal_record.json'))
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
$allRun = @($record.checks | Where-Object name -eq 'all')[0]
if ($allRun.exit_code -ne 0) { throw 'The recorded all-case command did not succeed.' }
$demoRoot = $allRun.output_directory

function Read-RecordedJson([string]$Name) {
    $file = Join-Path $demoRoot $Name
    $key = 'all/' + $Name
    $expected = $record.artifacts.PSObject.Properties[$key].Value
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing recorded artifact: $file" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $actual = [System.BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($file))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($actual -ne $expected) {
        throw "Recorded artifact hash differs: $file. Do not present it as the saved rehearsal."
    }
    Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
}

$summary = Read-RecordedJson 'build_summary.json'
if (-not $summary.all_expectations_met) { throw 'Unexpected outcome in the recorded build.' }
Write-Output "Saved offline rehearsal: $($record.rehearsal_id)"
Write-Output "Captured UTC: $($record.prepared_at_utc)"
Write-Output "HEAD: $($record.head)"
Write-Output "Scope: $($summary.integration_scope); backend: $($summary.backend_type); model: $($summary.model_execution_mode)"
Write-Output "Artifact directory: $demoRoot"
Write-Output 'These are saved rehearsal results, not a new live execution or human review.'

Write-Output 'S03 valid: source-specific color bindings'
$s03 = Read-RecordedJson 'S03_valid_run.json'
$s03Response = @($s03.events | Where-Object event_type -eq 'agent_response')[0].payload
$s03Response.claim_support | Format-Table claim_key, value, perspective, source, confidence, evidence_id -AutoSize
Write-Output $s03Response.text

Write-Output 'S07 valid: useful unknown and distinct missing outcomes'
$s07 = Read-RecordedJson 'S07_valid_run.json'
$s07Response = @($s07.events | Where-Object event_type -eq 'agent_response')[0].payload
$s07Response.claims | ConvertTo-Json
@($s07.events | Where-Object event_type -eq 'tool_result') | ForEach-Object { $_.payload } |
    Select-Object tool_name, state, status, error_category, evidence | ConvertTo-Json -Depth 8
Write-Output $s07Response.text

Write-Output 'S07 injected evaluator fault: invented 22 C and intended rejection'
$fault = Read-RecordedJson 'S07_injected_fault_run.json'
@($fault.events | Where-Object event_type -eq 'agent_response')[0].payload.claims | ConvertTo-Json
$faultResult = Read-RecordedJson 'S07_injected_fault_result.json'
$faultResult.checks | Where-Object passed -eq $false | Format-Table name, detail -Wrap

Write-Output 'S08 injected movement request: rejection receipt'
$s08 = Read-RecordedJson 'S08_injected_fault_run.json'
$s08.events | Where-Object { $_.event_type -eq 'tool_result' -and $_.payload.tool_name -eq 'move_forward' } |
    ForEach-Object { $_.payload } | Select-Object call_id, state, authorized, executed, reason | Format-List
$physical = @($s08.events | Where-Object { $_.event_type -eq 'boundary_call' -and $_.payload.operation -eq 'move_forward' })
if ($physical.Count -ne 0) { throw 'Unexpected movement backend call.' }
Write-Output "Physical movement boundary calls: $($physical.Count)"

Write-Output 'S07 malformed control: contract error rather than unknown conclusion'
$control = Read-RecordedJson 'S07_malformed_probe_error.json'
$control | Select-Object status, error_category, evaluated, error_type, message | Format-List
