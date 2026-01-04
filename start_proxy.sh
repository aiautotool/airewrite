#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PORT=50010

echo "Starting proxy server loop on port $PORT..."
cd "$DIR" || exit 1

while true; do
    echo "Starting proxy.py..."
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 proxy.py
    
    EXIT_CODE=$?
    echo "Proxy server crashed with exit code $EXIT_CODE. Restarting in 1 second..."
    sleep 1
done
