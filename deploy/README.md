# Deployment Guide

This guide explains how to set up the automated deployment for the Stock Bot using GitHub Actions and Systemd.

## Prerequisites on Server (my-oracle)

1.  **Clone the Repository**
    Ensure the repository is cloned to `~/stock-bot` (or update the scripts accordingly).
    ```bash
    cd ~
    git clone https://github.com/YOUR_USERNAME/REPO_NAME.git stock-bot
    cd stock-bot
    ```

2.  **Install `uv`**
    If not already installed:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

3.  **Setup Environment Variables**
    Create a `.env` file in `~/stock-bot/` with your API keys and configuration.
    ```bash
    cp .env.example .env
    nano .env
    ```

4.  **Setup Systemd Service**
    Copy the service file and enable it.
    ```bash
    # Edit the service file if your paths are different
    nano deploy/stock-bot.service

    # Copy to systemd directory
    sudo cp deploy/stock-bot.service /etc/systemd/system/

    # Reload systemd
    sudo systemctl daemon-reload

    # Enable and Start the service
    sudo systemctl enable stock-bot
    sudo systemctl start stock-bot

    # Check status
    sudo systemctl status stock-bot
    ```

    *Note: `deploy.sh` uses `sudo systemctl restart stock-bot`. Ensure the `ubuntu` user has sudo privileges for this command without password, or configure sudoers. For simplicity in this setup, we assume standard sudo access.*

## GitHub Repository Settings

1.  Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2.  Add the following **Repository secrets**:
    -   `HOST`: `134.185.104.240`
    -   `USERNAME`: `ubuntu`
    -   `SSH_KEY`: (Content of your private key `oracle-ssh-key-2025-12-15.key`)

## How it works

1.  When you merge a PR into `main`, the GitHub Action triggers.
2.  It logs into your server via SSH.
3.  It executes `deploy/deploy.sh`, which:
    -   Pulls the latest code.
    -   Updates dependencies with `uv sync`.
    -   Restarts the `stock-bot` service.
