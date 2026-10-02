#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
/usr/bin/python3 -m unittest discover -s tests -v
