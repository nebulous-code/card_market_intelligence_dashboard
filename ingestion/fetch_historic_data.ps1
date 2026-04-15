# Fetch historic price data from PokemonPriceTracker for Alakazam (Base Set)
# Reads POKEMON_PRICE_TRACKER_API_KEY and PPT_OUTPUT_DIR from the .env file
# at the repo root (one directory above this script's location)
# Saves the full API response to historic_data.json in the output directory

param (
    [string]$EnvFile = $null
)

# ── Locate .env file ──────────────────────────────────────────────────────────

if (-not $EnvFile) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $EnvFile   = Join-Path (Split-Path -Parent $scriptDir) ".env"
}

if (-not (Test-Path $EnvFile)) {
    Write-Error "Could not find .env file at: $EnvFile"
    Write-Error "Expected location: one directory above this script (repo root)"
    exit 1
}

Write-Host "Loading .env from: $EnvFile"

# ── Load .env file ────────────────────────────────────────────────────────────

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    if ($line -match "^([^=]+)=(.*)$") {
        $key   = $Matches[1].Trim()
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        $envVars[$key] = $value
    }
}

# ── Validate required variables ───────────────────────────────────────────────

$apiKey    = $envVars["POKEMON_PRICE_TRACKER_API_KEY"]
$outputDir = $envVars["PPT_OUTPUT_DIR"]

if (-not $apiKey) {
    Write-Error "POKEMON_PRICE_TRACKER_API_KEY is missing or empty in $EnvFile"
    exit 1
}

if (-not $outputDir) {
    Write-Error "PPT_OUTPUT_DIR is missing or empty in $EnvFile"
    exit 1
}

# ── Ensure output directory exists ────────────────────────────────────────────

if (-not (Test-Path $outputDir)) {
    Write-Host "Output directory does not exist. Creating: $outputDir"
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

# ── Build request ─────────────────────────────────────────────────────────────

$baseUrl = "https://www.pokemonpricetracker.com/api/v2/cards"

$params = @{
    set            = "Base Set"
    search         = "Alakazam"
    includeHistory = "true"
    days           = "180"
    limit          = "1"
}

$queryString = ($params.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$([Uri]::EscapeDataString($_.Value))"
}) -join "&"

$url = "${baseUrl}?${queryString}"

$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type"  = "application/json"
}

# ── Make the request ──────────────────────────────────────────────────────────

Write-Host "Fetching historic price data for Alakazam (Base Set)..."
Write-Host "URL: $url"
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
} catch {
    Write-Error "API request failed: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Error "HTTP status code: $statusCode"
    }
    exit 1
}

# ── Save to JSON ──────────────────────────────────────────────────────────────

$outputPath = Join-Path $outputDir "historic_data.json"
$response | ConvertTo-Json -Depth 20 | Set-Content -Path $outputPath -Encoding UTF8

Write-Host "Done. Output saved to: $outputPath"

# ── Quick summary ─────────────────────────────────────────────────────────────

$card = $response.data | Select-Object -First 1
if ($card) {
    Write-Host ""
    Write-Host "Card       : $($card.name)"
    Write-Host "Set        : $($card.setName)"
    Write-Host "Number     : $($card.cardNumber)"
    Write-Host "Market     : `$$($card.prices.market)"
    $historyCount = if ($card.priceHistory) { $card.priceHistory.Count } else { 0 }
    Write-Host "History    : $historyCount data point(s) returned"

    if ($historyCount -eq 0) {
        Write-Host ""
        Write-Warning "No price history returned. Check that:"
        Write-Warning "  1. Your API key is on the paid tier (free tier only returns 3 days)"
        Write-Warning "  2. POKEMON_PRICE_TRACKER_API_KEY is correct in your .env file"
        Write-Warning "  3. PPT has historic data for this card"
    } else {
        Write-Host ""
        Write-Host "First history point : $($card.priceHistory[0].date) - `$$($card.priceHistory[0].market)"
        Write-Host "Last history point  : $($card.priceHistory[-1].date) - `$$($card.priceHistory[-1].market)"
    }
} else {
    Write-Host ""
    Write-Warning "No card returned. The search may not have matched anything."
    Write-Warning "Check that PPT recognizes 'Base Set' as a valid set name."
    Write-Warning "Try browsing https://www.pokemonpricetracker.com to find the exact set name."
}