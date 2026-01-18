#!/bin/bash
# Health Audit Runner - Execute via Railway

cd "$(dirname "$0")" || exit 1

# Run health audit script
python3 health_audit.py
