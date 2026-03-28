# TraceIQ — Configuration
# Built by @its_vicex

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8728359588:AAFecJ_-V19t_JipAB6j72gWUz4dpqL4dqQ"

# ── Anthropic (Claude AI) ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY = "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"

# ── Blockchain APIs ───────────────────────────────────────────────────────────
HELIUS_API_KEY     = "ef51cba2-3547-4569-9f9d-da3160585068"
BIRDEYE_API_KEY    = "1c94f5e241d54cef9ddb6aa667c4375f"
ETHERSCAN_API_KEY  = "NTQICIRC9X8N7GQR9UIFWUZUZWKNVC87IR"
BSCSCAN_API_KEY    = "NTQICIRC9X8N7GQR9UIFWUZUZWKNVC87IR"

# ── API Base URLs ─────────────────────────────────────────────────────────────
HELIUS_BASE        = "https://mainnet.helius-rpc.com"
HELIUS_API_BASE    = "https://api.helius.xyz/v0"
BIRDEYE_BASE       = "https://public-api.birdeye.so"
ETHERSCAN_BASE     = "https://api.etherscan.io/api"
BSCSCAN_BASE       = "https://api.bscscan.com/api"
DEXSCREENER_BASE   = "https://api.dexscreener.com/latest"

# ── Filters ───────────────────────────────────────────────────────────────────
MIN_WIN_RATE       = 0.80   # 80% minimum win rate
MAX_INACTIVE_DAYS  = 20     # wallet must have traded within 20 days
MIN_INACTIVE_DAYS  = 0      # active as recently as today
MIN_TRADES         = 5      # minimum trades to be considered
TOP_WALLET_LIMIT   = 10     # max wallets returned in /top command
