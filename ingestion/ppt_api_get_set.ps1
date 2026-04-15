Get-Content .env | Foreach-Object {
    $name, $value = $_.split('=')
    if ($name -and $name[0] -ne '#') { # Skip empty or comment lines
        Set-Item "Env:\$($name.Trim())" $value.Trim().Trim('"').Trim("'")
    }
}

$ppt_api_key = $env:POKEMON_PRICE_TRACKER_API_KEY


# 1. Define your headers in a hashtable
$headers = @{
    "Authorization" = "Bearer $ppt_api_key"
}

# 2. Set your endpoint URL
$url = 'https://www.pokemonpricetracker.com/api/v2/sets?language=english&sortBy=releaseDate&sortOrder=desc&limit=100&offset=0'

# 3. Execute the request
$response = Invoke-RestMethod -Uri $url -Method Get -Headers $headers

# 4. Access the data directly
$response | ConvertTo-Json -Depth 10 | Out-File "C:\Users\nlicalsi\Documents\Code\card_market_intelligence_dashboard\ingestion\api_output\output.json"
