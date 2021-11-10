#!/usr/bin/env bash
export  FLASK_RUN_PORT=8000;FLASK_DEBUG=0

python -m cProfile -o profiling.txt main.py
