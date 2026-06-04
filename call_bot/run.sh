#!/usr/bin/env bash
# Запуск бота. Предполагает, что .env находится рядом с этим скриптом.
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Создай .env из .env.example и заполни токены."
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python bot.py
