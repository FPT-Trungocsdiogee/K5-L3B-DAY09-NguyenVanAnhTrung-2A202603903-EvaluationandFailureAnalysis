[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
Set-Location $PSScriptRoot   # mọi đường dẫn bên dưới tương đối với src/
$SPEC = "config/metric_spec.yaml"
$BASE = "reports/baseline_v1.json"
$ok = $true

# 0. Sha của eval set phải trùng với baseline (đúng lỗi bạn vừa gặp)
$sha  = python -c "from pathlib import Path; from lab9.evalset import sha12; print(sha12(Path('data/eval/eval_set_v1.jsonl')))"
$bsha = python -c "import json; print(json.load(open('$BASE', encoding='utf-8'))['manifest']['eval_set_sha'])"
Write-Host "eval set $sha | baseline $bsha"
if ($sha -ne $bsha) { Write-Host "FAIL: baseline lệch eval set" -ForegroundColor Red; $ok = $false }

# 1. Evaluate and gate the PR swarm  (phải exit 0)
python -m lab9.eval --shape swarm --spec $SPEC --out reports/eval_pr.json
python -m lab9.gate --pr reports/eval_pr.json --baseline $BASE --spec $SPEC
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: gate chặn swarm" -ForegroundColor Red; $ok = $false }

# 2. Check the committed baseline and the M3 metric  (phải exit 0)
python -m lab9.ci_check --pr reports/eval_pr.json --baseline $BASE --spec $SPEC
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: ci_check" -ForegroundColor Red; $ok = $false }

# 3. Verify the gate accepts fixed  (phải exit 0)
python -m lab9.eval --shape fixed --spec $SPEC --out reports/eval_fixed.json
python -m lab9.gate --pr reports/eval_fixed.json --baseline $BASE --spec $SPEC
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: gate chặn fixed (báo nhầm)" -ForegroundColor Red; $ok = $false }

# 4. Verify the gate blocks seeded_regression  (phải exit 1 VÀ có pass_rate)
python -m lab9.eval --shape seeded_regression --spec $SPEC --out reports/eval_seeded_regression.json
$out = python -m lab9.gate --pr reports/eval_seeded_regression.json --baseline $BASE --spec $SPEC
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
if ($code -ne 1 -or -not ($out -match '^exit 1 — blocked: ([^,]+, )*pass_rate(, |$)')) {
    Write-Host "FAIL: seeded_regression phải bị chặn ở pass_rate (exit $code)" -ForegroundColor Red; $ok = $false
}

if ($ok) { Write-Host "`nTẤT CẢ XANH — push được" -ForegroundColor Green } else { Write-Host "`nCòn lỗi ở trên" -ForegroundColor Red }