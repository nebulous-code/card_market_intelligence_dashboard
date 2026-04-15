<#
.SYNOPSIS
    Search PokemonPriceTracker sets by name and return matching set IDs.

.DESCRIPTION
    Fetches all English sets from the PPT API and filters them by a loose
    case-insensitive name search. Results are printed to the console and
    saved to a JSON file in the directory specified by PPT_OUTPUT_DIR in .env.

.PARAMETER SearchTerm
    Partial set name to search for. Case-insensitive, matches anywhere in
    the name. e.g. "base" matches "Base Set", "Base Set 2", "Darkness Ablaze", etc.
    Omit to return all sets.

.EXAMPLE
    .\ppt_api_get_set.ps1 -SearchTerm "base"
    .\ppt_api_get_set.ps1 -SearchTerm "jungle"
    .\ppt_api_get_set.ps1
#>
param(
    [string]$SearchTerm = ""
)

# Resolve the script's own directory regardless of how it was invoked.
# $PSScriptRoot can be empty in PS5 when called as .\path\to\script.ps1 from a parent dir.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $scriptDir) { $scriptDir = Get-Location }

# The repo root is one level above the ingestion/ folder.
$repoRoot = Split-Path -Parent $scriptDir
$envPath = Join-Path $repoRoot ".env"

Write-Host "Script dir : $scriptDir"
Write-Host "Repo root  : $repoRoot"
Write-Host "Loading env: $envPath"

if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $name, $value = $_.split('=', 2)
        if ($name -and $name.Trim() -and $name[0] -ne '#') {
            $cleanName  = $name.Trim()
            $cleanValue = if ($value) { $value.Trim().Trim('"').Trim("'") } else { "" }
            Set-Item "Env:\$cleanName" $cleanValue
        }
    }
    Write-Host ".env loaded."
} else {
    Write-Warning ".env not found at $envPath"
}

$ppt_api_key = $env:POKEMON_PRICE_TRACKER_API_KEY
if (-not $ppt_api_key) {
    Write-Error "POKEMON_PRICE_TRACKER_API_KEY is not set. Add it to your .env file."
    exit 1
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

$headers = @{
    "Authorization" = "Bearer $ppt_api_key"
}

$url = 'https://www.pokemonpricetracker.com/api/v2/sets?language=english&sortBy=releaseDate&sortOrder=desc&limit=250&offset=0'

Write-Host "Fetching sets from PPT API..."
$response = Invoke-RestMethod -Uri $url -Method Get -Headers $headers

# The API wraps results in a 'data' property
$allSets = if ($response.data) { $response.data } else { $response }

# Filter by search term (case-insensitive substring match on name)
if ($SearchTerm) {
    $results = $allSets | Where-Object { $_.name -ilike "*$SearchTerm*" }
    Write-Host "Sets matching '$SearchTerm': $($results.Count)"
} else {
    $results = $allSets
    Write-Host "Total sets returned: $($results.Count)"
}

# Print results to console as a table.
# The 'name' column is the identifier used by the PPT pricing API (set= parameter).
# The 'id' column is PPT's internal GUID and is not used for price lookups.
Write-Host ""
Write-Host "NOTE: Use the 'name' value as the PPT set identifier (e.g. in set_identifiers table)."
Write-Host ""
$results | Select-Object name, releaseDate | Format-Table -AutoSize

# Save filtered results to JSON
$outputFile = Join-Path $outputDir "ppt_sets_search.json"
$results | ConvertTo-Json -Depth 10 | Out-File $outputFile -Encoding UTF8
Write-Host "Full results saved to: $outputFile"
