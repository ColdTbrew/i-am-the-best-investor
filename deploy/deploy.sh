#!/bin/bash
set -e

# Load environment variables just in case, or ensure user environment is correct
# Using full paths is safer in scripts

echo "🚀 Starting deployment..."

# 1. Update Code
echo "📥 Pulling latest code..."
git pull origin main

# 2. Update Dependencies
echo "📦 Updating dependencies..."
# Ensure uv is in path. If installed via curl | sh, it is usually in $HOME/.cargo/bin or $HOME/.local/bin
# If not found, you might need to add it to path or use absolute path
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
uv sync

# 3. Restart Service
echo "🔄 Restarting service..."
sudo systemctl restart stock-bot

echo "✅ Deployment complete!"
