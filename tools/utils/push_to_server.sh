#!/bin/bash

# Settings
REMOTE_USER="root"
REMOTE_HOST="sastserver"
REMOTE_DIR="/root/work/sast-combinator"

# 1. Sync project on remote machine
rsync -avz --delete --exclude '.git' --exclude '__pycache__' ../ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
