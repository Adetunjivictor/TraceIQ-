# TraceIQ — Configuration
# Keys are loaded from environment variables (Railway)
# Never hardcode secrets in this file!

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# ── Anthropic (Claude AI) ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# ── Blockchain APIs ───────────────────────────────────────────────────────────
HELIUS_API_KEY    = os.environ["HELIUS_API_KEY"]
BIRDEYE_API_KEY   = os.environ["BIRDEYE_API_KEY"]
ETHERSCAN_API_KEY = os.environ["ETHERSCAN_API_KEY"]
BSCSCAN_API_KEY   = os.environ["BSCSCAN_API_KEY"]

# ── API Base URLs ─────────────────────────────────────────────────────────────
HELIUS_BASE      = "https://mainnet.helius-rpc.com"
HELIUS_API_BASE  = "https://api.helius.xyz/v0"
BIRDEYE_BASE     = "https://public-api.birdeye.so"
ETHERSCAN_BASE   = "https://api.etherscan.io/api"
BSCSCAN_BASE     = "https://api.bscscan.com/api"
DEXSCREENER_BASE = "https://api.dexscreener.com/latest"

# ── Filters ───────────────────────────────────────────────────────────────────
MIN_WIN_RATE      = 0.80  # 80% minimum win rate
MAX_INACTIVE_DAYS = 20    # wallet must have traded within 20 days
MIN_TRADES        = 5     # minimum trades to be considered
TOP_WALLET_LIMIT  = 10    # max wallets returned in /top command
