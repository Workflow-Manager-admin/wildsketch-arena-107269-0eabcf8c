#!/bin/bash
cd /home/kavia/workspace/code-generation/wildsketch-arena-107269-0eabcf8c/drawing_game_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

