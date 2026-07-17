param(
    [string]$Python = 'python'
)

& $Python manage.py ops_runtime_snapshot @args
