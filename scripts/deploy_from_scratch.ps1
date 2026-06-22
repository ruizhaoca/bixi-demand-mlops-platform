param(
    [Parameter(Mandatory = $true)]
    [string]$MlflowAllowCidr,
    [string]$AwsProfile = "bixi",
    [string]$Region = "us-east-2",
    [string]$RunId = "cloud-2024",
    [int]$NTrials = 40,
    [string]$UiAllowCidr = "0.0.0.0/0",
    [string]$RepoRef = "main"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$infraDir = Join-Path $repoRoot "infra"
$overridePath = Join-Path $env:TEMP "bixi-batch-overrides.json"
$deploymentId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()

function Aws-Text {
    param([string[]]$Arguments)
    $value = & aws @Arguments --output text
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI command failed: aws $Arguments" }
    return ($value | Out-String).Trim()
}

$env:AWS_PROFILE = $AwsProfile
$env:AWS_DEFAULT_REGION = $Region
$env:CDK_DEFAULT_REGION = $Region
$env:BIXI_RUN_ID = $RunId

aws sso login --profile $AwsProfile
if ($LASTEXITCODE -ne 0) { throw "AWS SSO login failed" }
$env:CDK_DEFAULT_ACCOUNT = Aws-Text @(
    "sts", "get-caller-identity", "--query", "Account"
)

Push-Location $infraDir
try {
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Failed to install CDK dependencies" }
    npx.cmd --yes aws-cdk@2 --app "python app.py" bootstrap `
        "aws://$($env:CDK_DEFAULT_ACCOUNT)/$Region"
    if ($LASTEXITCODE -ne 0) { throw "CDK bootstrap failed" }
    npx.cmd --yes aws-cdk@2 --app "python app.py" deploy `
        BixiNetwork BixiStorage BixiMlflow BixiBatch `
        --require-approval never `
        -c "allow_cidr=$MlflowAllowCidr" `
        -c "run_id=$RunId"
    if ($LASTEXITCODE -ne 0) { throw "Base infrastructure deployment failed" }
}
finally {
    Pop-Location
}

$queue = Aws-Text @(
    "cloudformation", "describe-stacks", "--stack-name", "BixiBatch",
    "--region", $Region,
    "--query", "Stacks[0].Outputs[?OutputKey=='JobQueueName'].OutputValue | [0]"
)
$jobDefinition = Aws-Text @(
    "cloudformation", "describe-stacks", "--stack-name", "BixiBatch",
    "--region", $Region,
    "--query", "Stacks[0].Outputs[?OutputKey=='JobDefinitionName'].OutputValue | [0]"
)
$pipelineBucket = Aws-Text @(
    "ssm", "get-parameter", "--name", "/bixi/pipeline-bucket", "--region", $Region,
    "--query", "Parameter.Value"
)
$dataBucket = Aws-Text @(
    "ssm", "get-parameter", "--name", "/bixi/data-bucket", "--region", $Region,
    "--query", "Parameter.Value"
)
$mlflowUrl = Aws-Text @(
    "ssm", "get-parameter", "--name", "/bixi/mlflow-tracking-uri", "--region", $Region,
    "--query", "Parameter.Value"
)

$overrides = @{
    command = @(
        "--from", "ingest", "--targets", "both", "--run-id", $RunId,
        "--n-trials", "$NTrials"
    )
    environment = @(
        @{ name = "BIXI_PIPELINE_BUCKET"; value = $pipelineBucket },
        @{ name = "BIXI_DATA_BUCKET"; value = $dataBucket },
        @{ name = "MLFLOW_TRACKING_URI"; value = $mlflowUrl }
    )
}
$overrideJson = $overrides | ConvertTo-Json -Depth 5 -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($overridePath, $overrideJson, $utf8NoBom)
$overrideUri = "file:///" + ($overridePath -replace "\\", "/")

try {
    $submission = & aws batch submit-job `
        --region $Region `
        --job-name "bixi-pipeline-$RunId" `
        --job-queue $queue `
        --job-definition $jobDefinition `
        --container-overrides $overrideUri `
        --output json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Batch submission failed" }
    $jobId = $submission.jobId
    Write-Host "Batch job submitted: $jobId"

    do {
        Start-Sleep -Seconds 30
        $status = Aws-Text @(
            "batch", "describe-jobs", "--jobs", $jobId, "--region", $Region,
            "--query", "jobs[0].status"
        )
        Write-Host "Batch status: $status"
    } while ($status -notin @("SUCCEEDED", "FAILED"))

    if ($status -eq "FAILED") {
        $reason = Aws-Text @(
            "batch", "describe-jobs", "--jobs", $jobId, "--region", $Region,
            "--query", "jobs[0].statusReason"
        )
        throw "Batch pipeline failed: $reason"
    }
}
finally {
    Remove-Item -LiteralPath $overridePath -ErrorAction SilentlyContinue
}

Push-Location $infraDir
try {
    npx.cmd --yes aws-cdk@2 --app "python app.py" deploy BixiServe BixiUi `
        --require-approval never `
        -c "run_id=$RunId" `
        -c "ui_cidr=$UiAllowCidr" `
        -c "repo_ref=$RepoRef" `
        -c "deployment_id=$deploymentId"
    if ($LASTEXITCODE -ne 0) { throw "Serving deployment failed" }
}
finally {
    Pop-Location
}

$streamlitUrl = Aws-Text @(
    "cloudformation", "describe-stacks", "--stack-name", "BixiUi",
    "--region", $Region,
    "--query", "Stacks[0].Outputs[?OutputKey=='StreamlitUrl'].OutputValue | [0]"
)
Write-Host "Deployment complete: $streamlitUrl"
