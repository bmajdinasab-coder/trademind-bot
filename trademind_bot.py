import os
import json
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
WALLET = "TS19Z7pisbGsCLiTg7NdMLKKaAjHf7HYkN"
PRICE = "$2 USDT (TRC20)"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── States ───────────────────────────────────────────────────────────────────
PAIR, DIRECTION, ENTRY, EXIT, SL, SIZE, EMOTION, REASON = range(8)

# ── Paid users storage (در پروژه واقعی از دیتابیس استفاده کن) ───────────────
# فایل ساده JSON برای نگه داشتن کاربران پولی
PAID_FILE = "paid_users.json"

def load_paid():
    try:
        with open(PAID_FILE) as f:
            return set(json.load(f))
    except:
        return set()

def save_paid(paid_set):
    with open(PAID_FILE, "w") as f:
        json.dump(list(paid_set), f)

def is_free_used(user_id):
    try:
        with open("free_used.json") as f:
            used = set(json.load(f))
        return user_id in used
    except:
        return False

def mark_free_used(user_id):
    try:
        with open("free_used.json") as f:
            used = set(json.load(f))
    except:
        used = set()
    used.add(user_id)
    with open("free_used.json", "w") as f:
        json.dump(list(used), f)

def is_paid(user_id):
    return user_id in load_paid()

def add_paid(user_id):
    paid = load_paid()
    paid.add(user_id)
    save_paid(paid)

# ── AI Analysis ──────────────────────────────────────────────────────────────
def analyze_trade(data: dict) -> dict:
    pnl = None
    try:
        e, x = float(data["entry"]), float(data["exit"])
        pnl = ((x - e) / e * 100) if data["direction"] == "Long" else ((e - x) / e * 100)
        pnl = round(pnl, 2)
    except:
        pass

    prompt = f"""You are TradeMind, an expert crypto trading coach combining technical and psychological analysis.

Analyze this trade and return ONLY a JSON object (no markdown, no extra text):

{{
  "score": <0-100>,
  "verdict": "<Excellent / Good / Average / Poor>",
  "rr_ratio": "<R:R ratio>",
  "technical": "<2-3 sentence technical analysis>",
  "psychology": "<2-3 sentence psychological analysis>",
  "mistakes": ["<mistake 1>", "<mistake 2>"],
  "lessons": ["<lesson 1>", "<lesson 2>"],
  "next_time": "<one actionable tip>"
}}

Trade data:
- Pair: {data['pair']}
- Direction: {data['direction']}
- Entry: ${data['entry']}
- Exit: ${data['exit']}
- Stop Loss: {data.get('sl', 'Not set')}
- Position Size: {data.get('size', 'Not specified')}
- Emotional state: {data.get('emotion', 'Neutral')}
- Reason: {data.get('reason', 'Not provided')}
- P&L: {pnl}%"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text
    try:
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        return json.loads(match.group()), pnl
    except:
        return None, pnl

def format_result(result: dict, data: dict, pnl) -> str:
    score = result.get("score", 0)
    if score >= 75:
        score_emoji = "🟢"
    elif score >= 50:
        score_emoji = "🟡"
    else:
        score_emoji = "🔴"

    pnl_str = f"{'📈' if pnl and pnl >= 0 else '📉'} {pnl}%" if pnl is not None else "N/A"

    mistakes = "\n".join(f"  • {m}" for m in result.get("mistakes", []))
    lessons = "\n".join(f"  • {l}" for l in result.get("lessons", []))

    return f"""⚡ *TradeMind Analysis*

{score_emoji} *Score: {result['score']}/100* — {result['verdict']}

📊 *Trade Summary*
• Pair: {data['pair']} ({data['direction']})
• P&L: {pnl_str}
• R/R Ratio: {result.get('rr_ratio', 'N/A')}
• Emotion: {data.get('emotion', 'Neutral')}

📐 *Technical Analysis*
{result.get('technical', '')}

🧠 *Psychology*
{result.get('psychology', '')}

❌ *Mistakes*
{mistakes if mistakes else '  • None detected'}

✅ *Lessons*
{lessons if lessons else '  • Keep it up!'}

💡 *Next Trade Tip*
_{result.get('next_time', '')}_"""

# ── Handlers ─────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"""👋 Welcome to *TradeMind AI*, {user.first_name}!

I analyze your crypto trades — technically and psychologically — so you become a better trader.

🎁 Your *first analysis is FREE*
💳 After that: {PRICE} per analysis

Let's start! Use /analyze to submit a trade."""
    await update.message.reply_text(text, parse_mode="Markdown")

async def analyze_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_free_used(user_id) and not is_paid(user_id):
        kb = [[InlineKeyboardButton("💳 How to Pay", callback_data="how_to_pay")]]
        await update.message.reply_text(
            f"⚡ You've used your free analysis.\n\nUnlock the next one for *{PRICE}*.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    ctx.user_data.clear()
    await update.message.reply_text(
        "📊 Let's analyze your trade!\n\n*Step 1/8* — What trading pair?\n\nExample: `BTC/USDT`",
        parse_mode="Markdown"
    )
    return PAIR

async def get_pair(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["pair"] = update.message.text.upper()
    kb = [
        [InlineKeyboardButton("Long 📈", callback_data="Long"),
         InlineKeyboardButton("Short 📉", callback_data="Short")]
    ]
    await update.message.reply_text(
        f"*Step 2/8* — Direction?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return DIRECTION

async def get_direction(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["direction"] = query.data
    await query.edit_message_text(
        f"*Step 3/8* — Entry price?\n\nExample: `42500`",
        parse_mode="Markdown"
    )
    return ENTRY

async def get_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["entry"] = update.message.text
    await update.message.reply_text(
        "*Step 4/8* — Exit price?\n\nExample: `44200`",
        parse_mode="Markdown"
    )
    return EXIT

async def get_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["exit"] = update.message.text
    await update.message.reply_text(
        "*Step 5/8* — Stop Loss price? (or type `skip`)",
        parse_mode="Markdown"
    )
    return SL

async def get_sl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["sl"] = val if val.lower() != "skip" else "Not set"
    await update.message.reply_text(
        "*Step 6/8* — Position size? (or type `skip`)\n\nExample: `$500` or `0.1 BTC`",
        parse_mode="Markdown"
    )
    return SIZE

async def get_size(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["size"] = val if val.lower() != "skip" else "Not specified"
    kb = [
        [InlineKeyboardButton("😐 Neutral", callback_data="Neutral"),
         InlineKeyboardButton("💪 Confident", callback_data="Confident")],
        [InlineKeyboardButton("😰 Anxious", callback_data="Anxious"),
         InlineKeyboardButton("🚀 FOMO", callback_data="FOMO")],
        [InlineKeyboardButton("🤑 Greedy", callback_data="Greedy"),
         InlineKeyboardButton("😨 Fearful", callback_data="Fearful")],
        [InlineKeyboardButton("😤 Revenge", callback_data="Revenge Trading"),
         InlineKeyboardButton("😤 Overconfident", callback_data="Overconfident")],
    ]
    await update.message.reply_text(
        "*Step 7/8* — Your emotional state during this trade?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return EMOTION

async def get_emotion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["emotion"] = query.data
    await query.edit_message_text(
        "*Step 8/8* — Why did you enter this trade?\n\nDescribe your setup, signals, reasoning. (or type `skip`)",
        parse_mode="Markdown"
    )
    return REASON

async def get_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["reason"] = val if val.lower() != "skip" else "Not provided"

    await update.message.reply_text("⏳ Analyzing your trade... please wait.")

    result, pnl = analyze_trade(ctx.user_data)

    if not result:
        await update.message.reply_text("❌ Analysis failed. Please try /analyze again.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    mark_free_used(user_id)
    if is_paid(user_id):
        # consume one paid credit
        pass

    text = format_result(result, ctx.user_data, pnl)
    kb = [[InlineKeyboardButton("🔄 Analyze Another Trade", callback_data="new_trade")]]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ConversationHandler.END

async def how_to_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"""💳 *How to Unlock TradeMind*

1️⃣ Send *$2 USDT* on *TRC20 network* to:

`{WALLET}`

2️⃣ After sending, type /paid and send your *transaction hash (TX ID)*

3️⃣ We'll verify and unlock your analysis within minutes.

⚠️ Make sure to use *TRC20 (TRON)* network only.""",
        parse_mode="Markdown"
    )

async def paid_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please send your *transaction hash (TX ID)* so we can verify your payment:",
        parse_mode="Markdown"
    )

async def new_trade_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if is_free_used(user_id) and not is_paid(user_id):
        kb = [[InlineKeyboardButton("💳 How to Pay", callback_data="how_to_pay")]]
        await query.edit_message_text(
            f"⚡ Unlock your next analysis for *{PRICE}*.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text("Use /analyze to start a new trade analysis.")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Use /analyze to start again.")
    return ConversationHandler.END

# ── Admin: manually approve payment ──────────────────────────────────────────
# Usage: /approve 123456789  (user's telegram ID)
ADMIN_ID = None  # Set your own Telegram user ID here

async def approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(ctx.args[0])
        add_paid(target_id)
        await update.message.reply_text(f"✅ User {target_id} approved.")
        await ctx.bot.send_message(target_id, "✅ Payment verified! Use /analyze to get your next analysis.")
    except:
        await update.message.reply_text("Usage: /approve <user_id>")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("analyze", analyze_start)],
        states={
            PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pair)],
            DIRECTION: [CallbackQueryHandler(get_direction, pattern="^(Long|Short)$")],
            ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_entry)],
            EXIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_exit)],
            SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sl)],
            SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_size)],
            EMOTION: [CallbackQueryHandler(get_emotion)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("paid", paid_command))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(how_to_pay, pattern="^how_to_pay$"))
    app.add_handler(CallbackQueryHandler(new_trade_callback, pattern="^new_trade$"))

    print("TradeMind Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
