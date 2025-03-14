import os
import math
import time
import boto3
import base58
import random
import asyncio
import logging
import aiomysql
import warnings
import threading
import json
import aiofiles
import datetime
import pymysql.cursors
from dotenv import load_dotenv
from solders.keypair import Keypair
import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext, ContextTypes
from telegram.error import TimedOut, BadRequest

warnings.simplefilter("ignore")
load_dotenv()
logging.basicConfig(level=logging.ERROR)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DB_NAME = os.getenv('DATABASE_NAME')
DB_HOST = os.getenv('DATABASE_HOST')
DB_USER = os.getenv('DATABASE_USER')
DB_PASSWORD = os.getenv('DATABASE_PASSWORD')
CHANNELID = int(os.getenv('TELEGRAM_CHANNEL_ID', '0'))
TABLE_USERS = os.getenv('TABLE_USERS', 'tbl_users')
TABLE_LOTTERY = os.getenv('TABLE_LOTTERY', 'tbl_lottery_%s')
TABLE_PRIZES = os.getenv('TABLE_PRIZES', 'tbl_prizes')
bot = Bot(token=TOKEN)

kms_client = boto3.client(
    'kms',
    region_name=os.getenv('AWS_REGION'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

user_last_start_time = {}
START_COMMAND_COOLDOWN = 3
MAX_START_COMMAND_COOLDOWN = 30
user_spam_count = {}
user_notified = {}
FREE_ENTRIES_FILE = "free_entries.json"
DRAW_INFO_FILE = "draw_info.json"
TOTAL_FREE_ENTRIES = 200

GAME_MODES = {
    "medium": {"numbers_to_pick": 3, "range": 20, "entry_fee": 25000}
}

async def setup_database():
    pool = await aiomysql.create_pool(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        autocommit=True
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            await cursor.execute(f"USE {DB_NAME}")
            await cursor.execute(f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'%'")
            await cursor.execute("FLUSH PRIVILEGES")
            await cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {TABLE_USERS} (
                    user_id BIGINT PRIMARY KEY,
                    wallet_address TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    earned DOUBLE DEFAULT 0,
                    free_entry INT DEFAULT 0
                )
            ''')
            for mode in GAME_MODES:
                await cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS {TABLE_LOTTERY % mode} (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        wallet_address TEXT NOT NULL,
                        encrypted_private_key TEXT NOT NULL,
                        round DOUBLE DEFAULT 0,
                        entries JSON
                    )
                ''')
            await cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {TABLE_PRIZES} (
                    mode VARCHAR(10) PRIMARY KEY,
                    prize_pool DOUBLE DEFAULT 0
                )
            ''')
            await cursor.execute(f"SELECT COUNT(*) FROM {TABLE_PRIZES}")
            prize_count = (await cursor.fetchone())[0]
            if prize_count == 0:
                for mode in GAME_MODES:
                    await cursor.execute(f'''
                        INSERT INTO {TABLE_PRIZES} (mode, prize_pool)
                        VALUES (%s, %s)
                    ''', (mode, 0))
    pool.close()
    await pool.wait_closed()
    tasks = [monitor_lottery(mode) for mode in GAME_MODES]
    await asyncio.gather(*tasks)

async def load_remaining_free_entries():
    if os.path.exists(FREE_ENTRIES_FILE):
        with open(FREE_ENTRIES_FILE, "r") as f:
            data = json.load(f)
            return data.get("remaining", TOTAL_FREE_ENTRIES)
    return TOTAL_FREE_ENTRIES

async def save_remaining_free_entries(remaining):
    with open(FREE_ENTRIES_FILE, "w") as f:
        json.dump({"remaining": remaining}, f, indent=4)

async def update_user_free_entry(user_id, free_entry_count):
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"UPDATE {TABLE_USERS} SET free_entry = %s WHERE user_id = %s",
                (free_entry_count, user_id)
            )
    pool.close()
    await pool.wait_closed()

async def get_user_free_entry(user_id):
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"SELECT free_entry FROM {TABLE_USERS} WHERE user_id = %s",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    pool.close()
    await pool.wait_closed()

async def private_chat_only(update: Update, context: CallbackContext):
    return update.effective_chat.type == 'private'

async def create_start_task(update: Update, context: CallbackContext):
    if not await private_chat_only(update, context):
        return
    user_id = update.effective_user.id
    current_time = time.time()
    if user_id in user_last_start_time and (current_time - user_last_start_time[user_id]) < START_COMMAND_COOLDOWN:
        user_spam_count[user_id] = user_spam_count.get(user_id, 0) + 1
        cooldown_time = min(START_COMMAND_COOLDOWN + (user_spam_count[user_id] * 3), MAX_START_COMMAND_COOLDOWN)
        if user_id not in user_notified:
            user_notified[user_id] = True
            await update.message.reply_text(f"Please wait {cooldown_time} seconds before trying again.")
        return
    else:
        user_spam_count[user_id] = 0
        user_notified[user_id] = False
    user_last_start_time[user_id] = current_time
    asyncio.create_task(start(update, context, user_id))

async def start(update: Update, context: Application, user_id: int = None):
    if not await private_chat_only(update, context):
        return
    user_id = user_id or update.effective_user.id
    await asyncio.sleep(2.5)
    remaining_free_entries = await load_remaining_free_entries()
    wallet_address = None
    free_entry_count = await get_user_free_entry(user_id)
    balance_formatted = "0.000"
    spl_balance_formatted = "0"
    if wallet_address:
        balance = 0
        balance_formatted = f"{math.floor(balance * 1000) / 1000:.3f}"
        spl_balance = 0
        spl_balance_formatted = round(spl_balance)
    else:
        private_key = Keypair()
        wallet_address = str(private_key.pubkey())
        await asyncio.sleep(1)
        if remaining_free_entries > 0 and free_entry_count == 0:
            free_entry_count = 1
            remaining_free_entries -= 1
            await asyncio.gather(
                update_user_free_entry(user_id, free_entry_count),
                save_remaining_free_entries(remaining_free_entries)
            )
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT entries FROM {TABLE_LOTTERY % 'medium'} WHERE id = 1")
            result = await cursor.fetchone()
            total_entries = 0
            if result and result[0]:
                try:
                    entries = json.loads(result[0])
                    total_entries = len(entries)
                except json.JSONDecodeError:
                    total_entries = 0
            await cursor.execute(f"SELECT mode, prize_pool FROM {TABLE_PRIZES}")
            prize_pools = {row[0]: row[1] for row in await cursor.fetchall()}
    pool.close()
    await pool.wait_closed()
    draw_info = await load_draw_info("medium")
    next_draw_time = draw_info["next_draw_time"]
    if next_draw_time is None:
        next_draw_time = time.time() + 3600
        await save_draw_info("medium", draw_info["draw_number"], next_draw_time)
    utc_draw_time = datetime.datetime.fromtimestamp(next_draw_time, tz=datetime.timezone.utc)
    next_draw_str = utc_draw_time.strftime("%H:%M %d/%m/%Y")
    welcome_message = (
        f"🎰 *Hey, Welcome to Solttery!* 🎰\n\n"
        f"A fun lottery game with big prizes!\n\n"
        f"🎲 *How It Works:*\n"
        f"• Pick 3 numbers from 1 to 20\n"
        f"• Every entry increases the prize pool\n"
        f"• Match all three numbers, in any order, then you win!\n"
        f"• Prize Pool: {round(prize_pools.get('medium', 0) * 0.66)} SOLTTERY\n"
        f"• *Next Draw at:* {next_draw_str} UTC\n\n"
        f"💰 *Your Info:*\n"
        f"• *Sol Balance:* {balance_formatted} Sol\n"
        f"• *Token Balance:* {spl_balance_formatted}\n"
        f"• *Wallet:* `{wallet_address or 'Not set'}`\n"
        f"• *Entries for next draw:* {total_entries}\n"
        f"• *Free Entries:* {free_entry_count}\n"
        f"• *Free Entries Remaining:* {remaining_free_entries}/{TOTAL_FREE_ENTRIES}\n\n"
        f"✨ *Choose your numbers and go for the win!*"
    )
    keyboard = [
        [InlineKeyboardButton("🎲 Lottery (Match 3/20)", callback_data='medium_mode')],
        [InlineKeyboardButton("How to Play?", callback_data='info'), InlineKeyboardButton("Wallet", callback_data='wallet')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode="markdown")
    elif update.callback_query:
        await context.bot.send_message(chat_id=user_id, text=welcome_message, reply_markup=reply_markup, parse_mode="markdown")
    else:
        await context.bot.send_message(chat_id=user_id, text=welcome_message, reply_markup=reply_markup, parse_mode="markdown")

async def button(update: Update, context: Application):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async def handle_query():
        if query.data == 'info':
            await query.edit_message_text(
                f"*🎰 Solttery Lottery - How to Play*\n\n"
                f"1. Pick 3 numbers between 1 and 20.\n"
                f"2. Pay the entry fee.\n"
                f"3. Wait for the draw.\n"
                f"4. Match all three numbers to win!",
                parse_mode='Markdown'
            )
            await start(update, context, user_id=user_id)
        elif query.data == 'medium_mode':
            mode = "medium"
            config = GAME_MODES[mode]
            pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(f"SELECT prize_pool FROM {TABLE_PRIZES} WHERE mode = %s", (mode,))
                    prize_pool = (await cursor.fetchone() or [0])[0]
            pool.close()
            await pool.wait_closed()
            winnable_prize = prize_pool * 0.7
            await query.edit_message_text(
                f"*{mode.capitalize()} Mode*\n\n"
                f"Pick {config['numbers_to_pick']} numbers from 1-{config['range']}\n"
                f"Entry Fee: {config['entry_fee']} SOLTTERY\n"
                f"Prize: {winnable_prize:.3f} SOLTTERY\n\n"
                "Would you like to pick numbers or get random ones?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Pick Numbers", callback_data=f'pick_{mode}')],
                    [InlineKeyboardButton("Random Numbers", callback_data=f'random_{mode}')],
                    [InlineKeyboardButton("Cancel", callback_data='cancel')]
                ]),
                parse_mode='Markdown'
            )
        elif query.data.startswith('pick_'):
            mode = query.data.split('_')[1]
            config = GAME_MODES[mode]
            context.user_data['mode'] = mode
            context.user_data['numbers'] = []
            await show_number_picker(query, context, config, 1)
        elif query.data.startswith('random_'):
            mode = query.data.split('_')[1]
            config = GAME_MODES[mode]
            context.user_data['mode'] = mode
            numbers = sorted(random.sample(range(1, config['range'] + 1), config['numbers_to_pick']))
            context.user_data['numbers'] = numbers
            await confirm_entry(query, context, mode, numbers)
        elif query.data.startswith('number_'):
            mode = context.user_data.get('mode')
            if not mode:
                await query.edit_message_text("Please select a game mode first.")
                await start(update, context, user_id=user_id)
                return
            config = GAME_MODES[mode]
            number = int(query.data.split('_')[1])
            numbers = context.user_data.get('numbers', [])
            if number not in numbers:
                numbers.append(number)
                context.user_data['numbers'] = numbers
            if len(numbers) < config['numbers_to_pick']:
                await show_number_picker(query, context, config, len(numbers) + 1)
            else:
                await confirm_entry(query, context, mode, sorted(numbers))
        elif query.data.startswith('confirm_'):
            await query.edit_message_text("Processing...")
            mode = query.data.split('_')[1]
            config = GAME_MODES[mode]
            numbers = context.user_data.get('numbers', [])
            if not numbers or len(numbers) != config['numbers_to_pick']:
                await query.edit_message_text("Invalid entry.")
                await start(update, context, user_id=user_id)
                return
            free_entry = await get_user_free_entry(user_id)
            if free_entry > 0:
                await query.edit_message_text(
                    f"Entry confirmed!\nNumbers: {', '.join(map(str, numbers))}\n"
                    f"TX - Free entry\nWaiting for the draw...",
                    parse_mode='Markdown', disable_web_page_preview=True
                )
                await save_entry_free(mode, "placeholder_wallet", numbers)
                context.user_data.pop('mode', None)
                context.user_data.pop('numbers', None)
                await update_user_free_entry(user_id, 0)
                await start(update, context, user_id=user_id)
            else:
                await query.edit_message_text("Payment processing not implemented in public version.")
                await start(update, context, user_id=user_id)
        elif query.data == 'cancel':
            context.user_data.pop('mode', None)
            context.user_data.pop('numbers', None)
            await query.message.delete()
            await start(update, context, user_id=user_id)
        elif query.data == 'wallet':
            keyboard = [
                [InlineKeyboardButton("Secret Key", callback_data='secret_key')],
                [InlineKeyboardButton("Cancel", callback_data='cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Wallet options:", reply_markup=reply_markup)
        elif query.data == 'secret_key':
            await query.edit_message_text("Secret key retrieval not implemented in public version.")
            await start(update, context, user_id=user_id)
    asyncio.create_task(handle_query())

async def show_number_picker(query, context, config, pick_number):
    buttons = []
    for i in range(1, config['range'] + 1):
        if i % 5 == 1:
            buttons.append([])
        buttons[-1].append(InlineKeyboardButton(str(i), callback_data=f'number_{i}'))
    await query.edit_message_text(
        f"Pick number {pick_number}/{config['numbers_to_pick']} (1-{config['range']})",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def confirm_entry(query, context, mode, numbers):
    config = GAME_MODES[mode]
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT prize_pool FROM {TABLE_PRIZES} WHERE mode = %s", (mode,))
            prize_pool = (await cursor.fetchone() or [0])[0]
    pool.close()
    await pool.wait_closed()
    winnable_prize = prize_pool * 0.7
    await query.edit_message_text(
        f"Confirm your {mode.capitalize()} entry?\n"
        f"Numbers: {', '.join(map(str, numbers))}\n"
        f"Entry Fee: {config['entry_fee']} SOLTTERY\n"
        f"Prize: {winnable_prize:.3f} SOLTTERY",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm", callback_data=f'confirm_{mode}')],
            [InlineKeyboardButton("Cancel", callback_data='cancel')]
        ]),
        parse_mode='Markdown'
    )

async def save_entry(mode, wallet_address, numbers):
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f'''
                UPDATE {TABLE_LOTTERY % mode}
                SET entries = JSON_ARRAY_APPEND(entries, '$', %s)
                WHERE id = 1
            ''', (json.dumps({"wallet": wallet_address, "numbers": numbers}),))
            entry_fee = GAME_MODES[mode]["entry_fee"]
            await cursor.execute(f'''
                UPDATE {TABLE_PRIZES}
                SET prize_pool = prize_pool + %s
                WHERE mode = %s
            ''', (entry_fee, mode))
    pool.close()
    await pool.wait_closed()

async def save_entry_free(mode, wallet_address, numbers):
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f'''
                UPDATE {TABLE_LOTTERY % mode}
                SET entries = JSON_ARRAY_APPEND(entries, '$', %s)
                WHERE id = 1
            ''', (json.dumps({"wallet": wallet_address, "numbers": numbers}),))
    pool.close()
    await pool.wait_closed()

async def load_draw_info(mode):
    if os.path.exists(DRAW_INFO_FILE):
        with open(DRAW_INFO_FILE, "r") as f:
            data = json.load(f)
            return data.get(mode, {"draw_number": 1, "next_draw_time": None})
    return {"draw_number": 1, "next_draw_time": None}

async def save_draw_info(mode, draw_number, next_draw_time):
    data = {}
    if os.path.exists(DRAW_INFO_FILE):
        with open(DRAW_INFO_FILE, "r") as f:
            data = json.load(f)
    data[mode] = {"draw_number": draw_number, "next_draw_time": next_draw_time}
    with open(DRAW_INFO_FILE, "w") as f:
        json.dump(data, f, indent=4)

async def monitor_lottery(mode):
    config = GAME_MODES[mode]
    pool = await aiomysql.create_pool(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME, autocommit=True)
    draw_info = await load_draw_info(mode)
    round_number = draw_info["draw_number"]
    next_draw_time = draw_info["next_draw_time"]
    if next_draw_time is None:
        next_draw_time = time.time() + 3600
        await save_draw_info(mode, round_number, next_draw_time)
    while True:
        current_time = time.time()
        if current_time >= next_draw_time:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(f"SELECT entries FROM {TABLE_LOTTERY % mode} WHERE id = 1")
                    result = await cursor.fetchone()
                    entries = []
                    if result and result[0]:
                        try:
                            entries = json.loads(result[0])
                            entries = [json.loads(e) if isinstance(e, str) else e for e in entries]
                        except json.JSONDecodeError:
                            entries = []
                    winning_numbers = sorted(random.sample(range(1, config['range'] + 1), config['numbers_to_pick']))
                    winners = [entry for entry in entries if sorted(entry["numbers"]) == winning_numbers]
                    await cursor.execute(f"SELECT prize_pool FROM {TABLE_PRIZES} WHERE mode = %s", (mode,))
                    prize_pool = (await cursor.fetchone() or [0])[0]
                    winnable_amount = prize_pool * 0.66
                    remaining_pool = prize_pool * 0.34
                    if winners:
                        await cursor.execute(f"UPDATE {TABLE_PRIZES} SET prize_pool = %s WHERE mode = %s", (remaining_pool, mode))
                    await cursor.execute(f"UPDATE {TABLE_LOTTERY % mode} SET entries = '[]' WHERE id = 1")
                    round_number += 1
                    next_draw_time = time.time() + 3600
                    await save_draw_info(mode, round_number, next_draw_time)
        time_to_next_draw = next_draw_time - time.time()
        await asyncio.sleep(min(10, max(1, time_to_next_draw)))
    pool.close()
    await pool.wait_closed()

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", create_start_task))
    application.add_handler(CallbackQueryHandler(button))
    threading.Thread(target=async_init, daemon=True).start()
    application.run_polling()

def async_init():
    asyncio.run(setup_database())

if __name__ == '__main__':
    main()