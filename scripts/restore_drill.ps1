param(
    [string]$OutputDir = 'backups/drills',
    [switch]$KeepArchive,
    [string]$Python = 'python'
)

$command = @('manage.py', 'run_restore_drill', '--output-dir', $OutputDir)
if ($KeepArchive) {
    $command += '--keep-archive'
}
& $Python @command @args
