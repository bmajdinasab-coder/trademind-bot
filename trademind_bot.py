import os
import time
import json
import re
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
WALLET = "TS19Z7pisbGsCLiTg7NdMLKKaAjHf7HYkN"
PRICE = "$2 USDT (TRC20)"

PAIR, DIRECTION, ENTRY, EXIT, SL, SIZE, EMOTION, REASON = range(8)
FREE_FILE = "free_used.json"
PAID_FILE = "paid_users.json"

def load_json(path):
    try:
        with open(path) as f:
            return set(json.load(f))
    except:
        return set()

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(list(data), f)

def is_free_used(uid):
    return uid in load_json(FREE_FILE)

def mark_free_used(uid):
    data = load_json(FREE_FILE)
    data.add(uid)
    save_json(FREE_FILE, data)

def is_paid(uid):
    return uid in load_json(PAID_FILE)

def add_paid(uid):
    data = load_json(PAID_FILE)
    data.add(uid)
    save_json(PAID_FILE, data)

def calc_pnl(entry, exit_price, direction):
    try:
        e, x = float(entry), float(exit_price)
        pct = ((x - e) / e * 100) if direction == "Long" else ((e - x) / e * 100)
        return round(pct, 2)
    except:
        return None

def analyze_trade(data):
    pnl = calc_pnl(data.get("entry"), data.get("exit"), data.get("direction"))
    prompt = f"""You are TradeMind, an expert crypto trading coach.
Analyze this trade and return ONLY a JSON object, no markdown:

{{
  "score": <0-100>,
  "verdict": "<Excellent/Good/Average/Poor>",
  "rr_ratio": "<R:R>",
  "technical": "<2-3 sentences>",
  "psychology": "<2-3 sentences>",
  "mistakes": ["<mistake1>", "<mistake2>"],
  "lessons": ["<lesson1>", "<lesson2>"],
  "next_time": "<one tip>"
}}

Trade:
- Pair: {data.get('pair')}
- Direction: {data.get('direction')}
- Entry: ${data.get('entry')}
- Exit: ${data.get('exit')}
- Stop Loss: {data.get('sl', 'Not set')}
- Size: {data.get('size', 'Not specified')}
- Emotion: {data.get('emotion', 'Neutral')}
- Reason: {data.get('reason', 'Not provided')}
- P&L: {pnl}%"""

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 1000}
            },
            timeout=30
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            print("No JSON found in Gemini response")
            return None, pnl
        return json.loads(match.group()), pnl
    except requests.exceptions.Timeout:
        print("Gemini API timeout")
        return None, pnl
    except requests.exceptions.HTTPError as e:
        print(f"Gemini HTTP error: {e} - {response.text}")
        return None, pnl
    except Exception as e:
        print(f"Gemini error: {e}")
        return None, pnl

def format_result(result, data, pnl):
    score = result.get("score", 0)
    emoji = "🟢" if score >= 75 else ("🟡" if score >= 50 else "🔴")
    pnl_str = f"{'📈' if pnl and pnl >= 0 else '📉'} {pnl}%" if pnl is not None else "N/A"
    mistakes = "\n".join(f"  • {m}" for m in result.get("mistakes", []))
    lessons = "\n".join(f"  • {l}" for l in result.get("lessons", []))
    return f"""⚡ *TradeMind Analysis*

{emoji} *Score: {result['score']}/100* — {result['verdict']}

📊 *Summary*
• Pair: {data['pair']} ({data['direction']})
• P&L: {pnl_str}
• R/R: {result.get('rr_ratio', 'N/A')}
• Emotion: {data.get('emotion', 'Neutral')}

📐 *Technical*
{result.get('technical', '')}

🧠 *Psychology*
{result.get('psychology', '')}

❌ *Mistakes*
{mistakes or '  • None detected'}

✅ *Lessons*
{lessons or '  • Keep it up!'}

💡 *Next Trade Tip*
_{result.get('next_time', '')}_"""

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Welcome to *TradeMind AI*!\n\nI analyze your crypto trades.\n\n🎁 First analysis is *FREE*\n💳 After that: {PRICE}\n\nUse /analyze to start.",
        parse_mode="Markdown"
    )

async def analyze_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_free_used(uid) and not is_paid(uid):
        kb = [[InlineKeyboardButton("💳 How to Pay", callback_data="how_to_pay")]]
        await update.message.reply_text(
            f"⚡ You've used your free analysis.\n\nUnlock for *{PRICE}*.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    ctx.user_data.clear()
    await update.message.reply_text("📊 *Step 1/8* — Trading pair?\n\nExample: `BTC/USDT`", parse_mode="Markdown")
    return PAIR

async def get_pair(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["pair"] = update.message.text.upper()
    kb = [[
        InlineKeyboardButton("Long 📈", callback_data="Long"),
        InlineKeyboardButton("Short 📉", callback_data="Short")
    ]]
    await update.message.reply_text("*Step 2/8* — Direction?", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return DIRECTION

async def get_direction(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["direction"] = q.data
    await q.edit_message_text("*Step 3/8* — Entry price?\n\nExample: `42500`", parse_mode="Markdown")
    return ENTRY

async def get_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["entry"] = update.message.text
    await update.message.reply_text("*Step 4/8* — Exit price?\n\nExample: `44200`", parse_mode="Markdown")
    return EXIT

async def get_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["exit"] = update.message.text
    await update.message.reply_text("*Step 5/8* — Stop Loss? (or type `skip`)", parse_mode="Markdown")
    return SL

async def get_sl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["sl"] = "Not set" if val.lower() == "skip" else val
    await update.message.reply_text("*Step 6/8* — Position size? (or `skip`)\n\nExample: `$500`", parse_mode="Markdown")
    return SIZE

async def get_size(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["size"] = "Not specified" if val.lower() == "skip" else val
    kb = [
        [InlineKeyboardButton("😐 Neutral", callback_data="Neutral"),
         InlineKeyboardButton("💪 Confident", callback_data="Confident")],
        [InlineKeyboardButton("😰 Anxious", callback_data="Anxious"),
         InlineKeyboardButton("🚀 FOMO", callback_data="FOMO")],
        [InlineKeyboardButton("🤑 Greedy", callback_data="Greedy"),
         InlineKeyboardButton("😨 Fearful", callback_data="Fearful")],
        [InlineKeyboardButton("😤 Revenge", callback_data="Revenge Trading"),
         InlineKeyboardButton("🦅 Overconfident", callback_data="Overconfident")],
    ]
    await update.message.reply_text("*Step 7/8* — Emotional state?", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return EMOTION

async def get_emotion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["emotion"] = q.data
    await q.edit_message_text("*Step 8/8* — Why did you enter?\n\nDescribe your setup. (or `skip`)", parse_mode="Markdown")
    return REASON

async def get_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    ctx.user_data["reason"] = "Not provided" if val.lower() == "skip" else val
    await update.message.reply_text("⏳ Analyzing your trade... (may take up to 30 seconds)")
    result, pnl = analyze_trade(ctx.user_data)
    if not result:
        await update.message.reply_text("❌ Analysis failed. The AI service may be busy. Please try /analyze again.")
        return ConversationHandler.END
    mark_free_used(update.effective_user.id)
    kb = [[InlineKeyboardButton("🔄 Analyze Another", callback_data="new_trade")]]
    await update.message.reply_text(
        format_result(result, ctx.user_data, pnl),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ConversationHandler.END

async def how_to_pay_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        f"💳 *How to Unlock*\n\n1️⃣ Send *$2 USDT* on *TRC20* to:\n\n`{WALLET}`\n\n2️⃣ Type /paid and send your TX hash\n3️⃣ We verify and unlock within minutes\n\n⚠️ TRC20 network only",
        parse_mode="Markdown"
    )

async def paid_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send your *TX hash* for verification:", parse_mode="Markdown")

async def new_trade_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    if is_free_used(uid) and not is_paid(uid):
        kb = [[InlineKeyboardButton("💳 How to Pay", callback_data="how_to_pay")]]
        await q.edit_message_text(f"⚡ Unlock for *{PRICE}*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await q.edit_message_text("Use /analyze to start.")

async def approve_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        target = int(ctx.args[0])
        add_paid(target)
        await update.message.reply_text(f"✅ User {target} approved.")
        await ctx.bot.send_message(target, "✅ Payment verified! Use /analyze for your next trade.")
    except:
        await update.message.reply_text("Usage: /approve <user_id>")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Use /analyze to start again.")
    return ConversationHandler.END

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
        per_message=False,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("paid", paid_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(how_to_pay_cb, pattern="^how_to_pay$"))
    app.add_handler(CallbackQueryHandler(new_trade_cb, pattern="^new_trade$"))
    print("TradeMind Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    time.sleep(5)
    main()
