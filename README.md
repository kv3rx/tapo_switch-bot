# Tapo Smart Plug & SSH Controller Bot

## Description
A custom-built Telegram bot designed to manage local network infrastructure securely. It allows authenticated users to remotely control TP-Link Tapo smart plugs and execute SSH commands on local machines directly via Telegram. 

## Features
* **IoT Control:** Power on/off TP-Link Tapo smart plugs (e.g., Tapo P115) within the local network.
* **Remote SSH Execution:** Safely send commands to local servers or PCs (e.g., remote shutdown, reboot, or service management).
* **Access Control:** Strict authorization based on allowed Telegram User IDs to prevent unauthorized execution.
* **Containerized Deployment:** Fully supported Docker setup for isolated and fast deployment.
* **Secure Configuration:** Environment variables are used for credential management, ensuring no hardcoded passwords.

## Prerequisites
* Python 3.9+ (if running locally) or Docker.
* A configured TP-Link Tapo smart plug in the local network.
* Target machines with SSH enabled and accessible.

## Configuration (.env)
Before running the bot, rename `.env.example` to `.env` and fill in your actual credentials. Your file should look like this:

```env
BOT_TOKEN=your_token_here
ALLOWED_ID=123456789
TAPO_USER=your-login
TAPO_PASS=your_password
TAPO_IP=192.168.x.x
TARGET_PC_IP=192.168.x.x
TARGET_PC_USER=pc_name\\user
TARGET_PC_PASS=pc_password
```

## Installation & Setup

### Option 1: Running via Docker (Recommended)
Running the bot inside a Docker container ensures an isolated environment without the need to install Python dependencies on your host machine.

1. Clone the repository:
   ```bash
   git clone https://github.com/kv3rx/tapo_switch-bot.git
   cd tapo_switch-bot
   ```
2. Build the Docker image:
   ```bash
   docker build -t tapo-bot .
   ```
3. Run the container (make sure your `.env` file is configured):
   ```bash
   docker run -d --name tapo_controller --env-file .env tapo-bot
   ```

### Option 2: Running Locally (Python)
1. Clone the repository and navigate to the directory.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```bash
   python tapoSwich.py
   ```

## Security Best Practices
Always ensure that your `.env` file is included in your `.gitignore` to prevent leaking sensitive API tokens, SSH passwords, and internal IP structures to the public repository.