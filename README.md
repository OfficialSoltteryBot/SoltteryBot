# Solttery - Telegram Lottery Bot

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Telegram](https://img.shields.io/badge/Telegram-Bot-green) ![MySQL](https://img.shields.io/badge/Database-MySQL-orange) ![AWS](https://img.shields.io/badge/AWS-KMS-yellow)

Solttery is a Telegram-based lottery game where players can pick numbers, enter draws, and win prizes in SOLTTERY tokens. Built with Python, it integrates with Telegram, MySQL, and AWS KMS for a secure and engaging user experience.

## Features
- **Lottery Gameplay**: Pick 3 numbers from 1-20 in Medium mode to enter the lottery.
- **Prize Pool**: Dynamic prize pool that grows with each entry (66% awarded to winners).
- **Free Entries**: Limited free entries for new users (200 total).
- **Wallet Integration**: Generates Solana keypairs for users (payment processing not included in public version).
- **Automated Draws**: Hourly draws with random number generation.
- **Telegram Interface**: Interactive buttons and commands via Telegram bot.

## Tech Stack
- **Python**: Core language with asyncio for asynchronous operations.
- **Telegram Bot API**: Handles user interaction via `python-telegram-bot`.
- **MySQL**: Stores user data, lottery entries, and prize pools using `aiomysql`.
- **AWS KMS**: Secure key management (configured via environment variables).
- **Solana**: Keypair generation via `solders` for wallet addresses.
- **Environment Variables**: Managed with `python-dotenv`.

## Prerequisites
- Python 3.8+
- MySQL server
- AWS account with KMS access
- Telegram Bot Token (obtained from Telegram's BotFather)

## Installation

1. **Clone the Repository**
   ```bash
   git clone <your-repository-url>
   cd solttery

**Install Dependencies**
bash
pip install -r requirements.txt
Set Up Environment Variables
Create a .env file in the root directory with placeholders for your own credentials:
TELEGRAM_BOT_TOKEN=<your-telegram-bot-token>
DATABASE_NAME=<your-database-name>
DATABASE_HOST=<your-database-host>
DATABASE_USER=<your-database-user>
DATABASE_PASSWORD=<your-database-password>
TELEGRAM_CHANNEL_ID=<your-channel-id>
AWS_REGION=<your-aws-region>
AWS_ACCESS_KEY_ID=<your-aws-access-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-key>

**Initialize the Database**
Run the script to set up the database schema:
bash
python main.py
Usage
Start the Bot
bash
python main.py
Interact via Telegram
Send /start to the bot in a private chat.
Follow the prompts to pick numbers or get random ones.
View your wallet, free entries, and draw info.

**Game Rules**
Medium Mode:
Pick 3 numbers from 1-20.
Entry fee: 25,000 SOLTTERY (or use a free entry).
Match all 3 numbers (in any order) to win.
Draws occur hourly.

**Project Structure**
solttery/
├── main.py              # Main bot logic
├── free_entries.json    # Tracks remaining free entries
├── draw_info.json       # Stores draw schedules
├── .env                 # Environment variables (not tracked in Git)
└── README.md            # This file

**Configuration**
Cooldowns: 
START_COMMAND_COOLDOWN: 3 seconds (increases with spam attempts).
MAX_START_COMMAND_COOLDOWN: 30 seconds.
Game Modes: Configurable in GAME_MODES dictionary.
Database Tables: Customizable via TABLE_USERS, TABLE_LOTTERY, and TABLE_PRIZES env vars.
Limitations
Payment processing and secret key retrieval are not implemented in this public version.
Assumes a single lottery round per mode (id=1 in database).

**Contributing**
Fork the repository.
Create a feature branch (git checkout -b feature/your-feature).
Commit your changes (git commit -m "Add your feature").
Push to the branch (git push origin feature/your-feature).
Open a Pull Request.

**License**
This project is licensed under the MIT License - see the LICENSE file for details (create one if needed).
Acknowledgments

Built with ❤️ by the Solttery team
