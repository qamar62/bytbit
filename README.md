# Bybit Trading Telegram Bot

A Telegram bot for trading on Bybit with features like checking balance, positions, orders, and placing trades.

## Features

- Check wallet balance
- View open positions
- View open orders
- Place new orders
- User-friendly inline keyboard interface

## Setup

1. Make sure you have Docker and Docker Compose installed
2. Clone this repository
3. Create a `.env` file with your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   BYBIT_API_KEY=your_bybit_api_key
   BYBIT_SECRET_KEY=your_bybit_secret_key
   ```
4. Build and run the bot:
   ```bash
   docker-compose up --build
   ```

## Usage

1. Start the bot by sending `/start` command
2. Use the inline keyboard buttons to:
   - Check your wallet balance
   - View open positions
   - View open orders
   - Place new orders

## Security

- API keys are stored in `.env` file (not committed to version control)
- Docker container runs in isolated environment
- Secure connection to Bybit API
"# bytbit" 
