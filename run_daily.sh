#!/usr/bin/env bash
# run_daily.sh — wrapper for cron
#
# Add to crontab (runs at 8 AM every day):
#   crontab -e
#   0 8 * * * /bin/bash /home/user/Job-Hunt/run_daily.sh
#
# To use a virtual environment, uncomment and adjust the line below:
# source /home/user/Job-Hunt/.venv/bin/activate

set -euo pipefail
cd "$(dirname "$0")"

python3 main.py
