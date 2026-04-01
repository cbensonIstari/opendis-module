#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install opendis pydantic
