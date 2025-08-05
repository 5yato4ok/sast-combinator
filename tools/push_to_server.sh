#!/bin/bash

# Настройки
REMOTE_USER="root"
REMOTE_HOST="sastserver"
REMOTE_DIR="/root/work/sast-combinator"

# 1. Синхронизировать проект на удалённую машину
rsync -avz --delete --exclude '.git' --exclude '__pycache__' ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
