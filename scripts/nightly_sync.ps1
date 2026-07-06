$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$imaScript = "C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs"
$publishRoot = Join-Path $repo ".nightly-publish"
$worktreeDir = Join-Path $publishRoot "worktree"
$stagingDir = Join-Path $publishRoot "staging"
$pagesRelativePath = "site_output\_pages"
$pagesArtifactDir = Join-Path $repo $pagesRelativePath
$today = Get-Date -Format "yyyy-MM-dd"
$imaSyncSummary = $null

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Script
    )

    Write-Output "== $Label =="
    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Reset-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

try {
    Write-Output "== nightly sync start =="
    Write-Output "repo: $repo"
    Write-Output "date: $today"

    Set-Location $repo

    Write-Output "== ima sync =="
    $imaOutput = (& python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script $imaScript) 2>&1
    foreach ($line in $imaOutput) {
        Write-Output $line
        if ($line -is [string] -and $line.StartsWith("IMA_SYNC_RESULT=")) {
            $imaSyncSummary = $line.Substring("IMA_SYNC_RESULT=".Length) | ConvertFrom-Json
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "ima sync failed with exit code $LASTEXITCODE"
    }

    $skipPublishForQuota = $false
    if ($null -ne $imaSyncSummary) {
        $skipPublishForQuota = (
            $imaSyncSummary.status -eq "partial" -and
            $imaSyncSummary.quota_exhausted -eq $true -and
            [int]$imaSyncSummary.rendered_pages -eq 0 -and
            [int]$imaSyncSummary.updated_indexes -eq 0
        )
    }

    if ($skipPublishForQuota) {
        Write-Output "quota-limited partial sync without new pages; skipping publish"
        Write-Output "== nightly sync done =="
        return
    }

    Invoke-Step -Label "pages build" -Script {
        python run_fetcher.py --config config.ima.json --mode pages
    }

    if (-not (Test-Path -LiteralPath $pagesArtifactDir)) {
        throw "pages artifact not found: $pagesArtifactDir"
    }

    if (Test-Path -LiteralPath $publishRoot) {
        Remove-Item -LiteralPath $publishRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null

    Invoke-Step -Label "prepare publish worktree" -Script {
        git worktree add --detach $worktreeDir HEAD
    }

    Reset-Directory -Path $stagingDir
    Copy-Item -LiteralPath (Join-Path $pagesArtifactDir '*') -Destination $stagingDir -Recurse -Force
    $noJekyll = Join-Path $pagesArtifactDir ".nojekyll"
    if (Test-Path -LiteralPath $noJekyll) {
        Copy-Item -LiteralPath $noJekyll -Destination (Join-Path $stagingDir ".nojekyll") -Force
    }

    $worktreePagesDir = Join-Path $worktreeDir $pagesRelativePath
    Reset-Directory -Path $worktreePagesDir
    Copy-Item -LiteralPath (Join-Path $stagingDir '*') -Destination $worktreePagesDir -Recurse -Force
    if (Test-Path -LiteralPath (Join-Path $stagingDir ".nojekyll")) {
        Copy-Item -LiteralPath (Join-Path $stagingDir ".nojekyll") -Destination (Join-Path $worktreePagesDir ".nojekyll") -Force
    }

    Set-Location $worktreeDir
    $statusOutput = git status --porcelain -- $pagesRelativePath
    if ([string]::IsNullOrWhiteSpace($statusOutput)) {
        Write-Output "no pages changes detected"
    } else {
        Invoke-Step -Label "commit publish artifact" -Script {
            git add $pagesRelativePath
            git commit -m "chore: daily sync $today"
            git push origin HEAD:main
        }
        Write-Output "pages changes committed and pushed"
    }

    Write-Output "== nightly sync done =="
}
finally {
    Set-Location $repo
    if (Test-Path -LiteralPath $worktreeDir) {
        git worktree remove $worktreeDir --force | Out-Null
    }
    if (Test-Path -LiteralPath $publishRoot) {
        Remove-Item -LiteralPath $publishRoot -Recurse -Force
    }
}
