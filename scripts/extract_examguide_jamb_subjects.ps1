param(
    [string]$ExamGuideRoot = "E:\NDGA\SCHOOL FOLDER\ExamGuide UTME 2026",
    [string]$OutDir = "E:\NDGA\exports\examguide-jamb-all-20260619"
)

$ErrorActionPreference = "Stop"

$subjectMap = @(
    @{ Folder = "English"; Bank = "English" },
    @{ Folder = "Mathematics"; Bank = "Mathematics" },
    @{ Folder = "Physics"; Bank = "Physics" },
    @{ Folder = "Chemistry"; Bank = "Chemistry" },
    @{ Folder = "Biology"; Bank = "Biology" },
    @{ Folder = "Government"; Bank = "Government" },
    @{ Folder = "Commerce"; Bank = "Commerce" },
    @{ Folder = "Economics"; Bank = "Economics" },
    @{ Folder = "Accounts"; Bank = "Accounting" },
    @{ Folder = "CRK"; Bank = "CRS" },
    @{ Folder = "Literature"; Bank = "Literature" },
    @{ Folder = "The Lekki Headmaster"; Bank = "Literature" },
    @{ Folder = "Computer Studies"; Bank = "Computer" },
    @{ Folder = "Geography"; Bank = "Geography" },
    @{ Folder = "Agriculture"; Bank = "Agriculture" }
)

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
    throw "Could not locate ExamGuide loader."
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
    throw "Could not locate loader singleton field."
}
$singletonField.SetValue($null, $loader)

$pastType = $asm.GetTypes() |
    Where-Object { $_.FullName -eq "TestDriller.PastQuestionAIFunction" } |
    Select-Object -First 1
if (-not $pastType) {
    throw "Could not locate PastQuestionAIFunction."
}

$rows = New-Object System.Collections.Generic.List[object]
$summary = New-Object System.Collections.Generic.List[object]

foreach ($subject in $subjectMap) {
    $folder = [string]$subject.Folder
    $bank = [string]$subject.Bank
    $subjectDir = Join-Path $ExamGuideRoot "app\res\data\em1\obj\$folder"
    if (-not (Test-Path $subjectDir)) {
        $summary.Add([ordered]@{ folder = $folder; bank = $bank; seasons = 0; rows = 0; status = "missing_folder" })
        continue
    }

    $startCount = $rows.Count
    $seasons = Get-ChildItem -Path $subjectDir -Filter "*.tdx" | Sort-Object Name | ForEach-Object { $_.BaseName }
    foreach ($season in $seasons) {
        $past = [Activator]::CreateInstance($pastType)
        $dict = New-Object "System.Collections.Generic.Dictionary[string,object]"
        $dict["exam_type"] = "Objective"
        $dict["subject"] = $folder
        $dict["season"] = $season
        $dict["question_indices"] = (1..100 -join ",")
        $pastType.GetProperty("ParameterData").SetValue($past, $dict)
        $result = $pastType.GetMethod("Execute").Invoke($past, @())
        $data = ($result.GetType().GetFields("Instance,Public,NonPublic") |
            Where-Object { $_.FieldType -eq [object] } |
            Select-Object -First 1).GetValue($result)

        foreach ($qno in ($data.Keys | Sort-Object { [int]$_ })) {
            $q = $data[$qno]
            $options = @($q["opt"])
            $rows.Add([ordered]@{
                bank_subject = $bank
                source_folder = $folder
                source = "ExamGuide UTME 2026"
                season = $season
                source_question_no = [int]$qno
                question_html = [string]$q["que"]
                options_html = @($options)
                explanation_html = [string]$q["sol"]
                topic = [string]$q["top"]
            })
        }
    }
    $summary.Add([ordered]@{
        folder = $folder
        bank = $bank
        seasons = $seasons.Count
        rows = $rows.Count - $startCount
        status = "ok"
    })
}

$rawJson = Join-Path $OutDir "examguide_jamb_raw_all.json"
$rows | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $rawJson

$summaryCsv = Join-Path $OutDir "extract_summary.csv"
$summary | Export-Csv -NoTypeInformation -Encoding UTF8 $summaryCsv

[pscustomobject]@{
    subjects = $summary.Count
    rows = $rows.Count
    json = $rawJson
    summary = $summaryCsv
} | ConvertTo-Json
