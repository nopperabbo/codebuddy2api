#!/bin/bash
# Start codebuddy2api server
cd "$(dirname "$0")"

# Activate venv and run
exec venv/bin/python web.py
