#!/bin/bash
set -a
source /home/ubuntu/brasileira/.env
set +a
export PYTHONPATH="/home/ubuntu/brasileira:/home/ubuntu/brasileira/motor_rss"
export S4_MAX_POSTS_PER_CYCLE=30
export S4_CYCLE_INTERVAL=45
exec /home/ubuntu/brasileira/venv/bin/python -m s4_fotografia
