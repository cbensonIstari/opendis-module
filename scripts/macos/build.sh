#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
source .venv/bin/activate
pip install pyinstaller
pyinstaller --onefile --collect-all opendis --name opendis_module opendis_module/__main__.py
cp dist/opendis_module .
