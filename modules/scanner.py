"""
TraceIQ — Scanner Module
/scan  → analyze wallet address
/pnl   → extract wallet from PNL card image
"""

import asyncio
from datetime import datetime, timezone
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd, fmt_pct,
    helius_transactions, birdeye_wallet_pnl,
    etherscan_txlist, dexscreener_search,
    find_social_links, claude_analyze, claude_analyze_image
)


# ── Analyze wallet address ────────────────────────────────────────────────────
async def analyze_wallet(address: str) -> str:
    address = address.strip()
    chain = detect_chain(address)

    if chain == "solana":
        return await _analyze_solana_wallet(address)
    elif chain == "evm":
        # Try ETH first, then BNB
        result = await _analyze_evm_wallet(address, "eth")
        return result
    else:
        return "❌ Invalid address format. Please paste a valid Solana or EVM wallet address."


# ── Solana wallet analysis ────────────────────────────────────────────────────
async def _analyze_solana_wallet(address: str) -> str:
    txs, pnl_data = await asyncio.gather(
        helius_transactions(address, limit=100),
        birdeye_wallet_pnl(address)
    )

    if not txs:
        return f"❌ No transaction history found for `{short_addr(address)}`"

    # Last active
    last_ts = txs[0].get("timestamp", 0) if txs else 0
    days_ago = days_since(last_ts) if last_ts else 999

    # Basic stats from transactions
    total_txs = len(txs)

    # Active status
    if days_ago <= 7:
        active_tag = "🟢 Very Active"
    elif days_ago <= 20:
        active_tag = "🟡 Active"
    else:
        active_tag = "🔴 Inactive"

    # Token holdings from birdeye
    tokens = pnl_data.get("items", [])
    token_count = len(tokens)
    total_value = sum(float(t.get("valueUsd", 0)) for t in tokens)

    # Build token list
    token_lines = ""
    for t in tokens[:5]:
        sym   = t.get("symbol", "?")
        val   = fmt_usd(t.get("valueUsd", 0))
        token_lines += f"  • {sym}: {val}\n"

    # AI summary
    ai_prompt = f"""You are TraceIQ, a crypto wallet intelligence bot.
Analyze this Solana wallet briefly:
- Address: {address}
- Last active: {days_ago} days ago
- Total transactions (last 100): {total_txs}
- Token holdings: {token_count} tokens, total value ~{fmt_usd(total_value)}
- Top tokens: {[t.get('symbol','?') for t in tokens[:5]]}

Give a 2-3 sentence wallet personality summary. Focus on trading behavior, activity level, and any notable patterns. Be direct and useful for a crypto trader."""

    ai_summary = await claude_analyze(ai_prompt)

    msg = (
        f"🔍 *Wallet Analysis*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 `{address}`\n"
        f"⛓ Chain: Solana\n"
        f"📅 Last Active: {days_ago}d ago  {active_tag}\n"
        f"📊 Transactions: {total_txs} (recent)\n"
        f"💼 Portfolio: {token_count} tokens | {fmt_usd(total_value)}\n\n"
    )

    if token_lines:
        msg += f"*Top Holdings:*\n{token_lines}\n"

    msg += f"*🤖 AI Summary:*\n_{ai_summary}_\n\n"
    msg += f"🔗 [View on Solscan](https://solscan.io/account/{address})"

    return msg


# ── EVM wallet analysis ───────────────────────────────────────────────────────
async def _analyze_evm_wallet(address: str, chain: str) -> str:
    txs = await etherscan_txlist(address, chain)
    chain_name = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer   = f"https://etherscan.io/address/{address}" if chain == "eth" else f"https://bscscan.com/address/{address}"

    if not txs:
        # Try BNB if ETH has no results
        if chain == "eth":
            return await _analyze_evm_wallet(address, "bnb")
        return f"❌ No transaction history found for `{short_addr(address)}`"

    last_ts  = int(txs[0].get("timeStamp", 0))
    days_ago = days_since(last_ts)

    if days_ago <= 7:
        active_tag = "🟢 Very Active"
    elif days_ago <= 20:
        active_tag = "🟡 Active"
    else:
        active_tag = "🔴 Inactive"

    total_txs = len(txs)
    # Unique contracts interacted with
    contracts = set(tx.get("to", "") for tx in txs if tx.get("to"))
    eth_sent  = sum(int(tx.get("value", 0)) for tx in txs if tx.get("from", "").lower() == address.lower())
    eth_sent_fmt = fmt_usd(eth_sent / 1e18 * 2000)  # rough ETH price estimate

    ai_prompt = f"""You are TraceIQ, a crypto wallet intelligence bot.
Analyze this {chain_name} wallet briefly:
- Address: {address}
- Last active: {days_ago} days ago
- Total recent transactions: {total_txs}
- Unique contracts interacted: {len(contracts)}
- Estimated ETH/BNB sent: {eth_sent/1e18:.4f}

Give a 2-3 sentence wallet personality summary for a crypto trader. Focus on activity, behavior patterns, and risk profile."""

    ai_summary = await claude_analyze(ai_prompt)

    msg = (
        f"🔍 *Wallet Analysis*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 `{address}`\n"
        f"⛓ Chain: {chain_name}\n"
        f"📅 Last Active: {days_ago}d ago  {active_tag}\n"
        f"📊 Transactions: {total_txs} (recent)\n"
        f"🔀 Contracts Used: {len(contracts)}\n\n"
        f"*🤖 AI Summary:*\n_{ai_summary}_\n\n"
        f"🔗 [View on Explorer]({explorer})"
    )

    return msg


# ── PNL Card Image Scanner ────────────────────────────────────────────────────
async def analyze_pnl_image(image_bytes: bytes) -> str:
    prompt = """You are TraceIQ, a crypto wallet intelligence assistant.

This is a PNL (Profit and Loss) card image from a crypto trading platform.

Please extract ALL of the following if visible:
1. Wallet address (full or partial)
2. Username or display name
3. Win rate percentage
4. Total PNL (profit/loss amount)
5. Number of trades
6. Best trade
7. Any token names mentioned
8. Any social handles or links visible
9. The platform name (e.g. Photon, GMGN, Cielo, etc.)

Format your response EXACTLY like this:
WALLET: <address or "not visible">
USERNAME: <name or "not visible">
WIN_RATE: <percentage or "not visible">
PNL: <amount or "not visible">
TRADES: <number or "not visible">
BEST_TRADE: <amount or "not visible">
TOKENS: <comma separated or "not visible">
SOCIALS: <links/handles or "not visible">
PLATFORM: <name or "not visible">

If something is not clearly visible, write "not visible". Be precise."""

    raw = await claude_analyze_image(image_bytes, prompt)

    # Parse the structured response
    def extract(field):
        for line in raw.split("\n"):
            if line.startswith(f"{field}:"):
                val = line.split(":", 1)[-1].strip()
                return val if val.lower() != "not visible" else None
        return None

    wallet   = extract("WALLET")
    username = extract("USERNAME")
    win_rate = extract("WIN_RATE")
    pnl      = extract("PNL")
    trades   = extract("TRADES")
    best     = extract("BEST_TRADE")
    tokens   = extract("TOKENS")
    socials  = extract("SOCIALS")
    platform = extract("PLATFORM")

    msg = "📸 *PNL Card Analysis*\n━━━━━━━━━━━━━━━━━━━━━\n"

    if platform:
        msg += f"📱 Platform: {platform}\n"
    if username:
        msg += f"👤 User: {username}\n"
    if wallet:
        msg += f"📍 Wallet: `{wallet}`\n"
    if win_rate:
        msg += f"🎯 Win Rate: {win_rate}\n"
    if pnl:
        msg += f"💰 PNL: {pnl}\n"
    if trades:
        msg += f"📊 Trades: {trades}\n"
    if best:
        msg += f"🏆 Best Trade: {best}\n"
    if tokens:
        msg += f"🪙 Tokens: {tokens}\n"
    if socials:
        msg += f"🔗 Socials: {socials}\n"

    msg += "\n"

    # If we got a wallet, offer to analyze it
    if wallet and wallet != "not visible":
        chain = detect_chain(wallet)
        if chain != "unknown":
            msg += f"💡 _Use /scan and paste `{wallet}` for full wallet analysis_"
        else:
            msg += "⚠️ _Wallet address partially visible — full address needed for analysis_"
    else:
        msg += "⚠️ _No wallet address detected in this image_"

    return msg
