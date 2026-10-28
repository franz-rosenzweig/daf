# The self-test: the app built in build\Daf, on a sandbox Daf made from this checkout
# (tools/sandbox.py, with an empty state of its own and a made-up sign-in: nothing it does
# reaches the real Daf), with nobody at the keyboard. The Windows workflow runs it after
# every build; so can you, with Python 3.12 and Daf's requirements installed.
#
#   windows\selftest.ps1 [-App build\Daf\Daf.exe] [-Python python] [-Port 8441]
#
# It prints each check and leaves with the app's exit code: 0 when every check held.
# Partway through, the app asks (in the control folder) for the sandbox to stop and start
# again, to see the window move to its copy and back.
param([string]$App = "build\Daf\Daf.exe", [string]$Python = "python", [int]$Port = 8441)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot

$work = Join-Path ([IO.Path]::GetTempPath()) ("daf-selftest-" + [guid]::NewGuid().ToString('N'))
$state = Join-Path $work 'state'
$data = Join-Path $work 'Data'
$saved = Join-Path $work 'Saved'
$control = Join-Path $work 'control'
$results = Join-Path $work 'results.json'
$serverLog = Join-Path $work 'server.log'
foreach ($d in $state, $data, $saved, $control, (Join-Path $work 'vault'), (Join-Path $work 'kindle'), (Join-Path $work 'ingest')) {
    New-Item -ItemType Directory -Force $d | Out-Null
}

# the sandbox's own state, pointing at nothing real
$env:PYTHONPATH = $repo
$env:PYTHONIOENCODING = 'utf-8'
$env:DAF_STATE = $state
$env:DAF_VAULT = Join-Path $work 'vault'
$env:DAF_KINDLE_DIR = Join-Path $work 'kindle'
$env:DAF_CWA_INGEST = Join-Path $work 'ingest'
$env:DAF_FRESHRSS_URL = 'http://127.0.0.1:9'
$env:DAF_KOMGA_CONF = Join-Path $work 'komga.json'
'{"url": "http://127.0.0.1:9"}' | Out-File -Encoding ascii $env:DAF_KOMGA_CONF
$base = "http://127.0.0.1:$Port"

$cookie = & $Python -c "from daf import auth; auth.set_password('windows-selftest-only'); print(auth.make_cookie())"
if ($LASTEXITCODE -or -not $cookie) { throw "the sandbox's sign-in wasn't made" }
$cookie = "$cookie".Trim()

function Start-Daf {
    $p = Start-Process -FilePath $Python -ArgumentList @("`"$repo\tools\sandbox.py`"", '127.0.0.1', $Port) -PassThru -NoNewWindow `
        -RedirectStandardOutput $serverLog -RedirectStandardError "$serverLog.err"
    for ($i = 0; $i -lt 120; $i++) {
        try {
            if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$base/api/health").StatusCode -eq 200) { return $p }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "the sandbox Daf didn't answer"
}

function Stop-Daf($p) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force; $p.WaitForExit(10000) | Out-Null }
}

$server = Start-Daf
"sandbox Daf on $base"

$arguments = @('--selftest', '--data', "`"$data`"", '--base', $base, '--cookie', $cookie,
    '--save-dir', "`"$saved`"", '--server-control', "`"$control`"", '--out', "`"$results`"")
$process = Start-Process -FilePath (Resolve-Path $App) -ArgumentList $arguments -PassThru
$null = $process.Handle          # or the exit code is lost once it ends
$started = Get-Date
$said = ''
while (-not $process.HasExited) {
    $want = Join-Path $control 'want'
    if (Test-Path $want) {
        $w = (Get-Content $want -Raw).Trim()
        if ($w -ne $said) {
            if ($w -eq 'down') { Stop-Daf $server; "the sandbox Daf stopped, as the app asked" }
            elseif ($w -eq 'up') { $server = Start-Daf; "the sandbox Daf started again" }
            $said = $w
            Set-Content -Path (Join-Path $control 'now') -Value $w -Encoding ascii
        }
    }
    if (((Get-Date) - $started).TotalMinutes -gt 7) { $process.Kill(); "the self-test didn't finish in seven minutes"; break }
    Start-Sleep -Milliseconds 250
}
$process.WaitForExit()
$code = if ($process.ExitCode -eq $null) { 2 } else { $process.ExitCode }
Stop-Daf $server

if (Test-Path $results) {
    $report = Get-Content $results -Raw -Encoding utf8 | ConvertFrom-Json
    foreach ($check in $report.checks) {
        $mark = if ($check.ok) { 'ok  ' } else { 'FAIL' }
        if ($check.detail) { "$mark  $($check.name)  ($($check.detail))" } else { "$mark  $($check.name)" }
    }
} else {
    "no results were written"
}
if ($code -notin 0, 1) {
    # not the self-test's own answer: what Windows saw of the app going down
    "the app ended with $('0x{0:X8}' -f $code)"
    Get-WinEvent -FilterHashtable @{ LogName = 'Application'; StartTime = $started } -MaxEvents 20 -ErrorAction SilentlyContinue |
        Where-Object { $_.ProviderName -in 'Application Error', '.NET Runtime', 'Windows Error Reporting' } |
        ForEach-Object { "--- $($_.ProviderName)"; $_.Message }
}
$log = Join-Path $data 'daf.log'
if (Test-Path $log) { "--- daf.log"; Get-Content $log -Encoding utf8 }
if ($code -ne 0) {
    if (Test-Path $serverLog) { "--- server.log"; Get-Content $serverLog -Tail 40 -Encoding utf8 }
    if (Test-Path "$serverLog.err") {
        # each error the sandbox Daf met, once, with where in Daf's code it was
        "--- the sandbox Daf's errors"
        Get-Content "$serverLog.err" -Encoding utf8 |
            Select-String -Pattern '\\daf\\daf\\\w+\.py", line \d+, in \w+|^\w[\w.]*(Error|Exception)\b' |
            ForEach-Object { $_.Line.Trim() } | Select-Object -Unique -First 60
    }
}
# the workflow keeps what was saved and the window's picture with the build
New-Item -ItemType Directory -Force (Join-Path $repo 'build\selftest') | Out-Null
Copy-Item (Join-Path $saved '*') (Join-Path $repo 'build\selftest') -ErrorAction SilentlyContinue
if (Test-Path $results) { Copy-Item $results (Join-Path $repo 'build\selftest') }
exit $code
