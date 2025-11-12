#!/bin/bash
set -e

echo "Starting voice-live-agent application..."

# Change to server directory
cd /home/site/wwwroot

# Install dependencies if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Start the application with Hypercorn (ASGI server for Quart)
echo "Starting Hypercorn server..."
exec hypercorn server:app --bind 0.0.0.0:8000 --workers 4 --access-log -
