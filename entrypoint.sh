#!/bin/sh

python src/data_pipeline/parser.py
python src/data_pipeline/loader.py
python src/ai_agent/cli.py