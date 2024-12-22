import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from pybit.unified_trading import HTTP
import json
from decimal import Decimal

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize Bybit client
client = HTTP(
    testnet=False,
    api_key=os.getenv('BYBIT_API_KEY'),
    api_secret=os.getenv('BYBIT_SECRET_KEY')
)

# Conversation states
SYMBOL, ORDER_TYPE, SIDE, QUANTITY, PRICE, LEVERAGE = range(6)

# Store user data
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📊 Balance", callback_data='balance'),
            InlineKeyboardButton("📈 Positions", callback_data='positions')
        ],
        [
            InlineKeyboardButton("📝 Open Orders", callback_data='orders'),
            InlineKeyboardButton("🛠 Place Order", callback_data='place_order')
        ],
        [
            InlineKeyboardButton("❌ Cancel Orders", callback_data='cancel_orders'),
            InlineKeyboardButton("⚙️ Set Leverage", callback_data='set_leverage')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        "Welcome to Bybit Trading Bot! 🤖\n\n"
        "Commands:\n"
        "/start - Show main menu\n"
        "/cancel - Cancel current operation\n\n"
        "Select an option:"
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
    except AttributeError:
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
    
    return ConversationHandler.END

async def get_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = client.get_wallet_balance(
            accountType="UNIFIED"
        )
        balance_text = "💰 Wallet Balance:\n\n"
        
        if 'result' in balance and 'list' in balance['result']:
            total_usdt = Decimal('0')
            for account in balance['result']['list']:
                for coin in account['coin']:
                    if float(coin['walletBalance']) > 0:
                        balance_text += f"*{coin['coin']}*:\n"
                        balance_text += f"Balance: {float(coin['walletBalance']):.8f}\n"
                        balance_text += f"Available: {float(coin['availableToWithdraw']):.8f}\n"
                        if coin['coin'] == 'USDT':
                            total_usdt = Decimal(str(coin['walletBalance']))
                        else:
                            # Get latest price for non-USDT assets
                            try:
                                ticker = client.get_tickers(
                                    category="spot",
                                    symbol=f"{coin['coin']}USDT"
                                )
                                if 'result' in ticker and 'list' in ticker['result']:
                                    price = Decimal(ticker['result']['list'][0]['lastPrice'])
                                    value = Decimal(str(coin['walletBalance'])) * price
                                    total_usdt += value
                                    balance_text += f"Value in USDT: {float(value):.2f}\n"
                            except Exception:
                                pass
                        balance_text += "\n"
            
            balance_text += f"\n*Total Portfolio Value*: {float(total_usdt):.2f} USDT"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text=balance_text if balance_text != "💰 Wallet Balance:\n\n" else "No balance found",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in get_balance: {str(e)}")
        await update.callback_query.edit_message_text(f"Error fetching balance: {str(e)}")

async def get_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        positions = client.get_positions(
            category="linear",
            settleCoin="USDT"
        )
        position_text = "📊 *Current Positions*\n\n"
        
        if 'result' in positions and 'list' in positions['result']:
            total_pnl = Decimal('0')
            for position in positions['result']['list']:
                if float(position.get('size', 0)) > 0:
                    try:
                        entry_price = Decimal(str(position.get('avgPrice', '0')))
                        current_price = Decimal(str(position.get('markPrice', '0')))
                        size = Decimal(str(position.get('size', '0')))
                        unrealized_pnl = Decimal(str(position.get('unrealisedPnl', '0')))
                        leverage = position.get('leverage', 'N/A')
                        margin = position.get('positionIM', 'N/A')
                        side = position.get('side', 'N/A')
                        
                        # Calculate PnL percentage
                        if entry_price > 0:
                            if side == 'Buy':
                                pnl_percentage = ((current_price - entry_price) / entry_price) * 100
                            else:
                                pnl_percentage = ((entry_price - current_price) / entry_price) * 100
                        else:
                            pnl_percentage = Decimal('0')
                        
                        # Calculate ROE manually
                        if margin and margin != 'N/A' and Decimal(str(margin)) > 0:
                            roe = (unrealized_pnl / Decimal(str(margin))) * 100
                        else:
                            roe = Decimal('0')
                        
                        # Determine emojis and indicators based on position state
                        side_emoji = "🟢 Long" if side == "Buy" else "🔴 Short"
                        pnl_color = "🟢" if unrealized_pnl >= 0 else "🔴"
                        roe_color = "🟢" if roe >= 0 else "🔴"
                        price_trend = "📈" if current_price > entry_price else "📉"
                        
                        position_text += f"{'='*30}\n"
                        position_text += f"*{position['symbol']}* {price_trend}\n"
                        position_text += f"Side: {side_emoji}\n"
                        position_text += f"Size: {float(size)} ({leverage}x)\n"
                        position_text += f"Entry: ${float(entry_price):.4f}\n"
                        position_text += f"Current: ${float(current_price):.4f}\n\n"
                        
                        # PnL Information
                        position_text += f"*PnL Information:*\n"
                        pnl_text = f"{pnl_color} PnL: ${float(unrealized_pnl):.2f} ({float(pnl_percentage):.2f}%)\n"
                        position_text += pnl_text
                        
                        # ROE Information
                        if margin != 'N/A':
                            position_text += f"Margin: ${float(Decimal(str(margin)))} USDT\n"
                        position_text += f"{roe_color} ROE: {float(roe):.2f}%\n\n"
                        
                        total_pnl += unrealized_pnl
                    except (ValueError, TypeError, KeyError) as e:
                        logging.error(f"Error processing position data: {str(e)}")
                        continue
            
            if total_pnl != 0:
                position_text += f"{'='*30}\n"
                total_pnl_color = "🟢" if total_pnl >= 0 else "🔴"
                position_text += f"\n*Portfolio Summary:*\n"
                position_text += f"{total_pnl_color} *Total PnL: ${float(total_pnl):.2f} USDT*\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data='positions')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        no_positions_text = (
            "📊 *No Open Positions*\n\n"
            "Start trading by:\n"
            "1. Set leverage first\n"
            "2. Place a new order\n"
            "3. Monitor your positions here"
        )
        
        await update.callback_query.edit_message_text(
            text=position_text if position_text != "📊 *Current Positions*\n\n" else no_positions_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in get_positions: {str(e)}")
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            text="❌ Error fetching positions. Please try again.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def get_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders = client.get_open_orders(
            category="linear",
            settleCoin="USDT"
        )
        orders_text = "📝 Open Orders:\n\n"
        
        if 'result' in orders and 'list' in orders['result']:
            for order in orders['result']['list']:
                orders_text += f"*{order['symbol']}*:\n"
                orders_text += f"Order ID: {order['orderId']}\n"
                orders_text += f"Side: {order['side']}\n"
                orders_text += f"Price: {order['price']}\n"
                orders_text += f"Quantity: {order['qty']}\n"
                orders_text += f"Type: {order['orderType']}\n"
                orders_text += f"Status: {order['orderStatus']}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text=orders_text if orders_text != "📝 Open Orders:\n\n" else "No open orders",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in get_orders: {str(e)}")
        await update.callback_query.edit_message_text(f"Error fetching orders: {str(e)}")

async def start_place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("BTC/USDT", callback_data='symbol_BTCUSDT'),
            InlineKeyboardButton("ETH/USDT", callback_data='symbol_ETHUSDT')
        ],
        [
            InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(
        "Select trading pair:",
        reply_markup=reply_markup
    )
    return SYMBOL

async def select_order_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_menu':
        return await back_to_main_menu(update, context)
    
    symbol = query.data.split('_')[1]
    context.user_data['symbol'] = symbol
    
    keyboard = [
        [
            InlineKeyboardButton("Market", callback_data='type_market'),
            InlineKeyboardButton("Limit", callback_data='type_limit')
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected {symbol}\nChoose order type:",
        reply_markup=reply_markup
    )
    return ORDER_TYPE

async def select_side(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_menu':
        return await back_to_main_menu(update, context)
    
    order_type = query.data.split('_')[1]
    context.user_data['order_type'] = order_type
    
    keyboard = [
        [
            InlineKeyboardButton("Long", callback_data='side_buy'),
            InlineKeyboardButton("Short", callback_data='side_sell')
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Order Type: {order_type.upper()}\nChoose side:",
        reply_markup=reply_markup
    )
    return SIDE

async def enter_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_menu':
        return await back_to_main_menu(update, context)
    
    side = query.data.split('_')[1]
    context.user_data['side'] = side
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Enter quantity (in {context.user_data['symbol'][:3]}):",
        reply_markup=reply_markup
    )
    return QUANTITY

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quantity = float(update.message.text)
        context.user_data['quantity'] = quantity
        
        if context.user_data['order_type'] == 'limit':
            await update.message.reply_text(
                f"Enter limit price (in USDT):"
            )
            return PRICE
        else:
            return await place_order(update, context)
            
    except ValueError:
        await update.message.reply_text(
            "Invalid quantity. Please enter a valid number."
        )
        return QUANTITY

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        context.user_data['price'] = price
        return await place_order(update, context)
    except ValueError:
        await update.message.reply_text(
            "Invalid price. Please enter a valid number."
        )
        return PRICE

async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        order_data = {
            "category": "linear",
            "symbol": context.user_data['symbol'],
            "side": context.user_data['side'].upper(),
            "orderType": context.user_data['order_type'].upper(),
            "qty": context.user_data['quantity'],
        }
        
        if context.user_data['order_type'] == 'limit':
            order_data["price"] = context.user_data['price']
        
        result = client.place_order(**order_data)
        
        if result.get('retCode') == 0:
            order_text = "✅ Order placed successfully!\n\n"
            order_text += f"Symbol: {context.user_data['symbol']}\n"
            order_text += f"Type: {context.user_data['order_type'].upper()}\n"
            order_text += f"Side: {context.user_data['side'].upper()}\n"
            order_text += f"Quantity: {context.user_data['quantity']}\n"
            if context.user_data['order_type'] == 'limit':
                order_text += f"Price: {context.user_data['price']}\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'message'):
                await update.message.reply_text(order_text, reply_markup=reply_markup)
            else:
                await update.callback_query.edit_message_text(order_text, reply_markup=reply_markup)
        else:
            error_msg = f"❌ Order failed: {result.get('retMsg')}"
            if hasattr(update, 'message'):
                await update.message.reply_text(error_msg)
            else:
                await update.callback_query.edit_message_text(error_msg)
    except Exception as e:
        error_msg = f"❌ Error placing order: {str(e)}"
        if hasattr(update, 'message'):
            await update.message.reply_text(error_msg)
        else:
            await update.callback_query.edit_message_text(error_msg)
    
    return ConversationHandler.END

async def cancel_all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = client.cancel_all_orders(
            category="linear",
            settleCoin="USDT"
        )
        
        if result.get('retCode') == 0:
            message = "✅ All orders cancelled successfully!"
        else:
            message = f"❌ Failed to cancel orders: {result.get('retMsg')}"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text=message,
            reply_markup=reply_markup
        )
    except Exception as e:
        await update.callback_query.edit_message_text(f"Error cancelling orders: {str(e)}")

async def start_set_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("BTC/USDT", callback_data='leverage_BTCUSDT'),
            InlineKeyboardButton("ETH/USDT", callback_data='leverage_ETHUSDT')
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(
        "Select symbol to set leverage:",
        reply_markup=reply_markup
    )
    return SYMBOL

async def enter_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    symbol = query.data.split('_')[1]
    context.user_data['symbol'] = symbol
    
    await query.edit_message_text(
        f"Enter leverage (1-100) for {symbol}:"
    )
    return LEVERAGE

async def handle_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        leverage = int(update.message.text)
        if leverage < 1 or leverage > 100:
            await update.message.reply_text(
                "Leverage must be between 1 and 100. Please try again:"
            )
            return LEVERAGE
        
        result = client.set_leverage(
            category="linear",
            symbol=context.user_data['symbol'],
            buyLeverage=str(leverage),
            sellLeverage=str(leverage)
        )
        
        if result.get('retCode') == 0:
            message = f"✅ Leverage set to {leverage}x for {context.user_data['symbol']}"
        else:
            message = f"❌ Failed to set leverage: {result.get('retMsg')}"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            text=message,
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "Invalid leverage. Please enter a number between 1 and 100:"
        )
        return LEVERAGE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='start')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Operation cancelled.',
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("📊 Balance", callback_data='balance'),
            InlineKeyboardButton("📈 Positions", callback_data='positions')
        ],
        [
            InlineKeyboardButton("📝 Open Orders", callback_data='orders'),
            InlineKeyboardButton("🛠 Place Order", callback_data='place_order')
        ],
        [
            InlineKeyboardButton("❌ Cancel Orders", callback_data='cancel_orders'),
            InlineKeyboardButton("⚙️ Set Leverage", callback_data='set_leverage')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        "Welcome to Bybit Trading Bot! 🤖\n\n"
        "Commands:\n"
        "/start - Show main menu\n"
        "/cancel - Cancel current operation\n\n"
        "Select an option:"
    )
    
    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return ConversationHandler.END

def main():
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    
    # Conversation handler for placing orders
    order_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_place_order, pattern='^place_order$')],
        states={
            SYMBOL: [
                CallbackQueryHandler(select_order_type, pattern='^symbol_'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ],
            ORDER_TYPE: [
                CallbackQueryHandler(select_side, pattern='^type_'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ],
            SIDE: [
                CallbackQueryHandler(enter_quantity, pattern='^side_'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ],
            QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ],
            PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
        ]
    )
    application.add_handler(order_conv_handler)
    
    # Conversation handler for setting leverage
    leverage_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_set_leverage, pattern='^set_leverage$')],
        states={
            SYMBOL: [
                CallbackQueryHandler(enter_leverage, pattern='^leverage_'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ],
            LEVERAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_leverage),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(back_to_main_menu, pattern='^back_to_menu$')
        ]
    )
    application.add_handler(leverage_conv_handler)
    
    # Other callback handlers
    application.add_handler(CallbackQueryHandler(get_balance, pattern='^balance$'))
    application.add_handler(CallbackQueryHandler(get_positions, pattern='^positions$'))
    application.add_handler(CallbackQueryHandler(get_orders, pattern='^orders$'))
    application.add_handler(CallbackQueryHandler(cancel_all_orders, pattern='^cancel_orders$'))
    application.add_handler(CallbackQueryHandler(start, pattern='^start$'))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
