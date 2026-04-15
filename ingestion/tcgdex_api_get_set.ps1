<#
.SYNOPSIS
    Search TCGdex sets by name and return matching set IDs.

.DESCRIPTION
    Queries the TCGdex public API for sets whose name contains the search term.
    Results are printed to the console and saved to a JSON file in the directory
    specified by PPT_OUTPUT_DIR in .env (same directory used by ppt_api_get_set.ps1).
    No API key required.

.PARAMETER SearchTerm
    Partial set name to search for. Case-insensitive, matches anywhere in the name.
    e.g. "base" matches "Base Set", "Base Set 2", etc.
    Omit to return all sets.

.EXAMPLE
    .\tcgdex_api_get_set.ps1 -SearchTerm "base"
    .\tcgdex_api_get_set.ps1 -SearchTerm "jungle"
    .\tcgdex_api_get_set.ps1
#>
param(
    [string]$SearchTerm = ""
)

# Resolve the script's own directory regardless of how it was invoked.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $scriptDir) { $scriptDir = Get-Location }

# The repo root is one level above the ingestion/ folder.
$repoRoot = Split-Path -Parent $scriptDir
$envPath = Join-Path $repoRoot ".env"

if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $name, $value = $_.split('=', 2)
        if ($name -and $name.Trim() -and $name[0] -ne '#') {
            $cleanName  = $name.Trim()
            $cleanValue = if ($value) { $value.Trim().Trim('"').Trim("'") } else { "" }
            Set-Item "Env:\$cleanName" $cleanValue
        }
    }
}

# Output directory: read from env, fall back to api_output/ next to this script
$outputDir = $env:PPT_OUTPUT_DIR
if (-not $outputDir) {
    $outputDir = Join-Path $scriptDir "api_output"
    Write-Warning "PPT_OUTPUT_DIR not set in .env - writing to $outputDir"
}

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

# TCGdex supports server-side name filtering (case-insensitive partial match).
# Using it directly avoids pulling all sets when a search term is provided.
$baseUrl = "https://api.tcgdex.net/v2/en/sets"
if ($SearchTerm) {
    $url = "${baseUrl}?name=${SearchTerm}&sort:field=releaseDate&sort:order=DESC"
} else {
    $url = "${baseUrl}?sort:field=releaseDate&sort:order=DESC&pagination:itemsPerPage=500"
}

Write-Host "Fetching sets from TCGdex API..."
$response = Invoke-RestMethod -Uri $url -Method Get

if (-not $response) {
    Write-Host "No sets found matching '$SearchTerm'."
    exit 0
}

$count = if ($response -is [array]) { $response.Count } else { 1 }
if ($SearchTerm) {
    Write-Host "Sets matching '$SearchTerm': $count"
} else {
    Write-Host "Total sets returned: $count"
}

# Ensure we always work with an array
$results = @($response)

# NOTE: The 'id' column is the TCGdex set identifier used by the ingestion scripts
# (e.g. "base2" for Jungle). Use this value when calling register_identifier.
Write-Host ""
Write-Host "NOTE: Use the 'id' value as the TCGdex set identifier (e.g. in set_identifiers table)."
Write-Host ""
$results | Select-Object id, name, releaseDate | Format-Table -AutoSize

# Save results to JSON
$outputFile = Join-Path $outputDir "tcgdex_sets_search.json"
$results | ConvertTo-Json -Depth 10 | Out-File $outputFile -Encoding UTF8
Write-Host "Full results saved to: $outputFile"
