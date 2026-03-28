"""
TraceIQ — Wallet Intelligence Bot
Built for Victor Bliss | @its_vicex
Modules: PNL Scanner | Top Wallets | Dev Tracker | Social Linking
"""

import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from config import TELEGRAM_TOKEN
import modules.scanner as scanner
import modules.top_wallets as top_wallets
import modules.dev_tracker as dev_tracker

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
WAITING_FOR_IMAGE = 1
WAITING_FOR_CONTRACT_TOP = 2
WAITING_FOR_CONTRACT_DEV = 3
WAITING_FOR_WALLET_SCAN = 4


# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👁 <b>TraceIQ — Wallet Intelligence</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "I help you find and analyze high-performance wallets across Solana, ETH/Base &amp; BNB Chain.\n\n"
        "<b>Commands:</b>\n"
        "🔍 /scan — Analyze a wallet address\n"
        "📸 /pnl — Upload a PNL card to extract wallet\n"
        "🏆 /top — Find top wallets from a token contract\n"
        "🧑‍💻 /dev — Analyze dev wallet of a token\n"
        "❓ /help — Show this menu\n\n"
        "Built by @its_vicex"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


# ── /help ─────────────────────────────────────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)


# ── /scan ─────────────────────────────────────────────────────────────────────
async def scan_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 <b>Wallet Scanner</b>\n\nPaste a wallet address to analyze:\n<i>(Solana, ETH, or BNB)</i>",
        parse_mode="HTML"
    )
    return WAITING_FOR_WALLET_SCAN


async def scan_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    await update.message.reply_text("⏳ Scanning wallet... please wait")
    try:
        result = await scanner.analyze_wallet(address)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"scan_wallet error: {e}")
        await update.message.reply_text(f"❌ Error scanning wallet: {str(e)}")
    return ConversationHandler.END


# ── /pnl ──────────────────────────────────────────────────────────────────────
async def pnl_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 <b>PNL Card Scanner</b>\n\nSend me a PNL card image and I'll extract the wallet address + analyze it.",
        parse_mode="HTML"
    )
    return WAITING_FOR_IMAGE


async def pnl_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Reading PNL card... please wait")
    try:
        photo = update.message.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()
        result = await scanner.analyze_pnl_image(bytes(file_bytes))
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"pnl_image error: {e}")
        await update.message.reply_text(f"❌ Error reading image: {str(e)}")
    return ConversationHandler.END


# ── /top ──────────────────────────────────────────────────────────────────────
async def top_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏆 <b>Top Wallet Finder</b>\n\nPaste a token contract address to find the best performing wallets:\n<i>(80-100% win rate, active 7-20 days)</i>",
        parse_mode="HTML"
    )
    return WAITING_FOR_CONTRACT_TOP


async def top_contract(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    contract = update.message.text.strip()
    await update.message.reply_text("⏳ Hunting top wallets... this may take 15-30 seconds")
    try:
        result = await top_wallets.find_top_wallets(contract)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"top_contract error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
    return ConversationHandler.END


# ── /dev ──────────────────────────────────────────────────────────────────────
async def dev_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧑‍💻 <b>Dev Wallet Tracker</b>\n\nPaste a token contract address to analyze the deployer wallet:",
        parse_mode="HTML"
    )
    return WAITING_FOR_CONTRACT_DEV


async def dev_contract(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    contract = update.message.text.strip()
    await update.message.reply_text("⏳ Analyzing dev wallet... please wait")
    try:
        result = await dev_tracker.analyze_dev(contract)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"dev_contract error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Use /help to see commands.")
    return ConversationHandler.END


# ── Error handler ─────────────────────────────────────────────────────────────
async def error_handler(update, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {ctx.error}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    scan_conv = ConversationHandler(
        entry_points=[CommandHandler("scan", scan_start)],
        states={WAITING_FOR_WALLET_SCAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, scan_wallet)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    pnl_conv = ConversationHandler(
        entry_points=[CommandHandler("pnl", pnl_start)],
        states={WAITING_FOR_IMAGE: [MessageHandler(filters.PHOTO, pnl_image)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    top_conv = ConversationHandler(
        entry_points=[CommandHandler("top", top_start)],
        states={WAITING_FOR_CONTRACT_TOP: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_contract)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dev_conv = ConversationHandler(
        entry_points=[CommandHandler("dev", dev_start)],
        states={WAITING_FOR_CONTRACT_DEV: [MessageHandler(filters.TEXT & ~filters.COMMAND, dev_contract)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(scan_conv)
    app.add_handler(pnl_conv)
    app.add_handler(top_conv)
    app.add_handler(dev_conv)
    app.add_error_handler(error_handler)

    logger.info("TraceIQ is live!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
