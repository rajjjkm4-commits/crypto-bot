import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN          = "8598800608:AAHllMFYXsfyv5rTPaFtA7JcIJHv6P8dPVA"
ADMIN_CHAT_ID      = 1256115118
PRIVATE_GROUP_LINK = "https://t.me/+FgsZ3xFFKyxlNDhl"

REFERRAL_LINKS = {
    "CoinDCX": "https://invite.coindcx.com/27157291",
    "Mudrex":  "https://mudrex.go.link/2u3hZ",
    "Vantage": "https://vigco.co/la-com-inv/HQ5hNvyG",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

CHOOSING_APP, SUBMITTING_PROOF = range(2)

def init_db():
    conn = sqlite3.connect("bot.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            chosen_app TEXT,
            proof      TEXT,
            status     TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row

def save_user(user_id, username, full_name, chosen_app, proof):
    conn = sqlite3.connect("bot.db")
    conn.execute("""
        INSERT OR REPLACE INTO users (user_id, username, full_name, chosen_app, proof, status)
        VALUES (?,?,?,?,?,'pending')
    """, (user_id, username, full_name, chosen_app, proof))
    conn.commit()
    conn.close()

def update_status(user_id, status):
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)
    if existing:
        status = existing[5]
        if status == "approved":
            await update.message.reply_text(f"✅ You're already a member!\n\n👉 {PRIVATE_GROUP_LINK}")
            return ConversationHandler.END
        if status == "pending":
            await update.message.reply_text("⏳ Your request is under review. Please wait!")
            return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton("📈 CoinDCX", callback_data="app_CoinDCX")],
        [InlineKeyboardButton("💰 Mudrex",  callback_data="app_Mudrex")],
        [InlineKeyboardButton("🏦 Vantage", callback_data="app_Vantage")],
    ]
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        "To join our *exclusive private group*, complete one task:\n\n"
        "📌 Register on any crypto platform below using *my referral link*.\n\n"
        "👇 Choose a platform:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_APP

async def app_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    app_name = query.data.replace("app_", "")
    context.user_data["chosen_app"] = app_name
    link = REFERRAL_LINKS[app_name]
    await query.edit_message_text(
        f"Great choice! 🎉\n\n"
        f"*Step 1 —* Register on *{app_name}*:\n👉 {link}\n\n"
        f"*Step 2 —* Send your *UID or Email* from {app_name} as proof.\n\n"
        f"_⚡ Approved within 24 hours._",
        parse_mode="Markdown"
    )
    return SUBMITTING_PROOF

async def proof_submitted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    proof = update.message.text
    chosen_app = context.user_data.get("chosen_app", "Unknown")
    save_user(user.id, user.username, user.full_name, chosen_app, proof)
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{user.id}"),
    ]]
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"🔔 *New Request*\n\n"
            f"👤 {user.full_name}\n"
            f"🔗 @{user.username or 'N/A'}\n"
            f"🆔 `{user.id}`\n"
            f"📱 {chosen_app}\n"
            f"🪪 `{proof}`"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        "✅ *Proof submitted!*\n\nAdmin will approve within 24 hours. You'll be notified here! 🚀",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer("⛔ Not authorized!", show_alert=True)
        return
    await query.answer()
    action, uid = query.data.split("_", 1)
    user_id = int(uid)
    if action == "approve":
        update_status(user_id, "approved")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 *Approved!*\n\nHere's your group link:\n👉 {PRIVATE_GROUP_LINK}",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"✅ User `{user_id}` approved!", parse_mode="Markdown")
    elif action == "reject":
        update_status(user_id, "rejected")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ *Not approved.*\n\nPlease verify you used the referral link and /start again.",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"❌ User `{user_id}` rejected.", parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Type /start to begin again.")
    return ConversationHandler.END

async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    conn = sqlite3.connect("bot.db")
    rows = conn.execute("SELECT user_id, full_name, chosen_app, proof FROM users WHERE status='pending'").fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("✅ No pending requests.")
        return
    text = "*Pending:*\n\n" + "\n".join([f"`{r[0]}` | {r[1]} | {r[2]} | `{r[3]}`" for r in rows])
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_APP:     [CallbackQueryHandler(app_chosen, pattern="^app_")],
            SUBMITTING_PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, proof_submitted)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(approve|reject)_"))
    app.add_handler(CommandHandler("pending", pending))
    print("✅ Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
