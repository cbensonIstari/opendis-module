#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
rm -rf build/ dist/ .venv/ *.spec __pycache__ opendis_module/__pycache__
