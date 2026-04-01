#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
source .venv/bin/activate
pip install pytest
python -m pytest tests/ -v
