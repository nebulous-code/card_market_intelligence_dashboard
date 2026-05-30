#!/usr/bin/env bash
# Test the PokemonPriceTracker parse-title endpoint with various variant inputs.
# Reads POKEMON_PRICE_TRACKER_API_KEY and PPT_OUTPUT_DIR from .env in the
# same directory as this script. Saves each response as a separate JSON file.
#
# Usage:
#   ./test_parse_title.sh
#
# Requires: bash, curl, jq (for pretty-printing JSON)

set -euo pipefail

# ─── Edit this list to change the test cases ──────────────────────────────────
# Each line is one test input. Format:  test_id|title to send to the parser
# The test_id is used in the output filename and should be filename-safe.
TEST_CASES=(
    "01_charizard_black_dot|Charizard Black Dot NM"
    "02_red_cheek_pikachu|Red Cheek Pikachu LP"
    "03_blastoise_shadowless|Blastoise Base Set Shadowless NM"
    "04_machamp_first_edition|Base Set Machamp 1st Edition LP"
    "05_dark_arbok_wizards|Team Rocket Dark Arbok wizards edition"
    "06_pikachu_simple|Pikachu Base Set 58/102"
)
# ──────────────────────────────────────────────────────────────────────────────

# ─── Locate and load .env ─────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env file not found at $ENV_FILE" >&2
    exit 1
fi

echo "Loading .env from: $ENV_FILE"

# Read .env line by line, ignoring comments and blank lines
while IFS='=' read -r key value; do
    # Skip blank lines and comments
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    # Trim quotes and whitespace from the value
    key="$(echo "$key" | xargs)"
    value="$(echo "$value" | sed -e 's/^[[:space:]]*//;s/[[:space:]]*$//' -e 's/^"//;s/"$//' -e "s/^'//;s/'$//")"
    export "$key=$value"
done < "$ENV_FILE"

# ─── Validate required variables ──────────────────────────────────────────────

if [[ -z "${POKEMON_PRICE_TRACKER_API_KEY:-}" ]]; then
    echo "Error: POKEMON_PRICE_TRACKER_API_KEY is missing or empty in $ENV_FILE" >&2
    exit 1
fi

if [[ -z "${PPT_OUTPUT_DIR:-}" ]]; then
    echo "Error: PPT_OUTPUT_DIR is missing or empty in $ENV_FILE" >&2
    exit 1
fi

# ─── Ensure output directory exists ───────────────────────────────────────────

if [[ ! -d "$PPT_OUTPUT_DIR" ]]; then
    echo "Output directory does not exist. Creating: $PPT_OUTPUT_DIR"
    mkdir -p "$PPT_OUTPUT_DIR"
fi

# ─── Run each test case ───────────────────────────────────────────────────────

URL="https://www.pokemonpricetracker.com/api/v2/parse-title"

echo ""
echo "Running ${#TEST_CASES[@]} test case(s)..."
echo ""

for case in "${TEST_CASES[@]}"; do
    test_id="${case%%|*}"
    title="${case#*|}"
    output_file="${PPT_OUTPUT_DIR}/parse_test_${test_id}.json"

    echo "─────────────────────────────────────────────"
    echo "Test:  $test_id"
    echo "Title: $title"

    # Build JSON payload safely
    payload=$(jq -n \
        --arg title "$title" \
        '{title: $title, options: {fuzzyMatching: true, maxSuggestions: 3, includeConfidence: true}}')

    # Call the API
    response=$(curl -sS -X POST "$URL" \
        -H "Authorization: Bearer ${POKEMON_PRICE_TRACKER_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$payload")

    # Save pretty-printed JSON
    if echo "$response" | jq . > "$output_file" 2>/dev/null; then
        echo "Saved: $output_file"

        # Print a quick summary if jq can extract it
        match_count=$(echo "$response" | jq '.matches | length // 0')
        if [[ "$match_count" -gt 0 ]]; then
            top_name=$(echo "$response"        | jq -r '.matches[0].card.name        // "unknown"')
            top_set=$(echo "$response"         | jq -r '.matches[0].card.setName     // "unknown"')
            top_confidence=$(echo "$response"  | jq -r '.matches[0].confidence       // 0')
            echo "Match: $top_name ($top_set) — confidence $top_confidence"
        else
            echo "No matches returned."
        fi
    else
        # If response wasn't valid JSON, save raw and warn
        echo "$response" > "$output_file"
        echo "Warning: response was not valid JSON. Saved raw output to $output_file"
    fi

    echo ""
done

echo "─────────────────────────────────────────────"
echo "Done. Output saved to: $PPT_OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  1. Inspect the JSON files for variant fields"
echo "  2. Look for any 'parsed' or 'extracted' object alongside 'matches'"
echo "  3. Note which inputs returned high vs low confidence"
