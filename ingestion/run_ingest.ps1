param(
    [Parameter(Mandatory=$true)]
    [string]$SetId
)

uv run python run.py --set-id $SetId
