$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (Test-Path ".\.env") {
    Get-Content ".\.env" | ForEach-Object {
        if ($_ -match '^[A-Za-z_][A-Za-z0-9_]*=') {
            $parts = $_.Split('=', 2)
            [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
        }
    }
}

python -m pip install -r requirements.txt
python src\01_ingest.py
python src\02_cluster.py
python src\03_sentiment.py
python src\04_framing.py
python src\06_report.py
python src\07_dashboard.py
