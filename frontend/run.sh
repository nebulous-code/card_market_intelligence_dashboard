#!/bin/bash
# Starts the Vite development server for the Vue frontend on port 5173.
#
# Vite watches for file changes and hot-reloads the browser automatically,
# so edits to Vue components appear in the browser without a manual refresh.
#
# The frontend will be available at http://127.0.0.1:5173
#
# Note: The API server must be running on port 8000 before starting the
# frontend, otherwise the dashboard will show an error when it tries to
# load set data.
#
# Usage: ./run.sh

npm run dev
