param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('d','p')]
    [string]$db_env
)


Get-Content .env | Foreach-Object {
    # Only split on the FIRST equals sign
    $parts = $_.Split('=', 2)
    
    if ($parts.Count -eq 2) {
        $name  = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")

        if ($name -and $name[0] -ne '#') {
            Set-Item "Env:\$name" $value
        }
    }
}


if ($db_env -eq 'p') {
    $db_connection = $env:DATABASE_URL_PROD
} else {
    $db_connection = $env:DATABASE_URL
}

Write-Host "Connecting to: $db_env environment..." -ForegroundColor Cyan
& echo $db_connection
& psql "$db_connection"
