# Starts the FastAPI development server on port 8151.
#
# The server runs with --reload, which means it automatically restarts
# whenever a Python file in the api/ directory is saved. This is useful
# during development so you do not have to manually restart after every change.
#
# The server will be available at http://127.0.0.1:8151
# Interactive API docs are at http://127.0.0.1:8151/docs
#
# Usage: .\run.ps1

uv run uvicorn main:app --reload --port 8151
