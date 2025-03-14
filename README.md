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

**Game Rules**
Medium Mode:
Pick 3 numbers from 1-20.
Entry fee: 25,000 SOLTTERY (or use a free entry).
Match all 3 numbers (in any order) to win.
Draws occur hourly.

**Configuration**
Payment processing and secret key retrieval are not implemented in this public version.
Assumes a single lottery round per mode (id=1 in database).

**License**
This project is licensed under the MIT License - see the LICENSE file for details (create one if needed).
Acknowledgments

Built with ❤️ by the Solttery team
