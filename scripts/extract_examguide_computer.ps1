param(
    [string]$ExamGuideRoot = "E:\NDGA\SCHOOL FOLDER\ExamGuide UTME 2026",
    [string]$OutDir = "E:\NDGA\exports\examguide-computer-20260619"
)

$ErrorActionPreference = "Stop"

$exe = Join-Path $ExamGuideRoot "TestDriller.exe"
if (-not (Test-Path $exe)) {
    throw "TestDriller.exe not found at $exe"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$asm = [Reflection.Assembly]::LoadFrom($exe)

$loaderTypes = @(
    $asm.GetTypes() | Where-Object {
        $_.GetConstructors("Instance,Public,NonPublic") | Where-Object {
            $p = $_.GetParameters()
            $p.Count -eq 3 -and
                $p[0].ParameterType -eq [string] -and
                $p[1].ParameterType -eq [string] -and
                $p[2].ParameterType -eq [bool]
        }
    }
)

if ($loaderTypes.Count -lt 2) {
    throw "Could not locate ExamGuide content loader."
}

$loaderType = $loaderTypes[1]
$ctor = $loaderType.GetConstructors("Instance,Public,NonPublic") | Where-Object {
    $p = $_.GetParameters()
    $p.Count -eq 3 -and
        $p[0].ParameterType -eq [string] -and
        $p[1].ParameterType -eq [string] -and
        $p[2].ParameterType -eq [bool]
} | Select-Object -First 1

$loader = $ctor.Invoke([object[]]@(
    [string](Join-Path $ExamGuideRoot "app\res"),
    [string](Join-Path $ExamGuideRoot "app"),
    [bool]$true
))

$singletonField = $loaderType.GetFields("Static,Public,NonPublic") |
    Where-Object { $_.FieldType -eq $loaderType } |
    Select-Object -First 1

if (-not $singletonField) {
    throw "Could not locate ExamGuide loader singleton field."
}

$singletonField.SetValue($null, $loader)

$pastType = $asm.GetTypes() |
    Where-Object { $_.FullName -eq "TestDriller.PastQuestionAIFunction" } |
    Select-Object -First 1

if (-not $pastType) {
    throw "Could not locate PastQuestionAIFunction."
}

$subjectDir = Join-Path $ExamGuideRoot "app\res\data\em1\obj\Computer Studies"
$seasons = Get-ChildItem -Path $subjectDir -Filter "*.tdx" |
    Sort-Object Name |
    ForEach-Object { $_.BaseName }

$rows = New-Object System.Collections.Generic.List[object]

foreach ($season in $seasons) {
    $past = [Activator]::CreateInstance($pastType)
    $dict = New-Object "System.Collections.Generic.Dictionary[string,object]"
    $dict["exam_type"] = "Objective"
    $dict["subject"] = "Computer Studies"
    $dict["season"] = $season
    $dict["question_indices"] = (1..100 -join ",")
    $pastType.GetProperty("ParameterData").SetValue($past, $dict)
    $result = $pastType.GetMethod("Execute").Invoke($past, @())
    $data = ($result.GetType().GetFields("Instance,Public,NonPublic") |
        Where-Object { $_.FieldType -eq [object] } |
        Select-Object -First 1).GetValue($result)

    foreach ($qno in ($data.Keys | Sort-Object {[int]$_})) {
        $q = $data[$qno]
        $options = @($q["opt"])
        $rows.Add([ordered]@{
            subject = "Computer"
            source = "ExamGuide UTME 2026"
            season = $season
            source_question_no = [int]$qno
            question_html = [string]$q["que"]
            option_a_html = if ($options.Count -gt 0) { [string]$options[0] } else { "" }
            option_b_html = if ($options.Count -gt 1) { [string]$options[1] } else { "" }
            option_c_html = if ($options.Count -gt 2) { [string]$options[2] } else { "" }
            option_d_html = if ($options.Count -gt 3) { [string]$options[3] } else { "" }
            correct_source_index = 0
            explanation_html = [string]$q["sol"]
            topic = [string]$q["top"]
        })
    }
}

$rawJson = Join-Path $OutDir "computer_raw_examguide.json"
$rows | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $rawJson

$rawCsv = Join-Path $OutDir "computer_raw_examguide.csv"
$rows | Export-Csv -NoTypeInformation -Encoding UTF8 $rawCsv

[pscustomobject]@{
    seasons = $seasons.Count
    rows = $rows.Count
    json = $rawJson
    csv = $rawCsv
} | ConvertTo-Json
