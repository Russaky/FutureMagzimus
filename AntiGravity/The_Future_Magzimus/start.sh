#!/usr/bin/env bash

# Navigate to the project root directory
cd "$(dirname "$0")"

echo "Starting server..."
# Start the server in the background
python3 control/server/app.py &
SERVER_PID=$!

# Give the server a couple of seconds to bind to the port
sleep 2

echo "Opening Google Chrome..."
# Open the UI in Google Chrome
open -a "Google Chrome" "http://localhost:5000"

echo "Server is running (PID: $SERVER_PID). Press Ctrl+C to stop."

# Trap termination signals to kill the background server process when the script exits
trap "echo 'Stopping server...'; kill $SERVER_PID" EXIT INT TERM

# Wait for the server process to exit
wait $SERVER_PID
