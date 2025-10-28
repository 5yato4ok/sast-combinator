# Settings
REMOTE_USER="root"
REMOTE_HOST="sastserver"
REMOTE_DIR="/root/work/aist-defect-dojo"

# 1. Sync project on remote machine
rsync -avz --delete --exclude '.git' --exclude '__pycache__' --exclude 'sast-combinator/analyses_result' ../../../ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
