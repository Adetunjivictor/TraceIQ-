"""
TraceIQ — Scanner Module (v2)
/scan  → wallet profitability analysis over 7d and 20d
/pnl   → smart PNL card image analysis
"""

import asyncio
from datetime import datetime, timezone
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd,
    helius_transactions, etherscan_txlist,
    dexscreener_search, claude_analyze, claude_analyze_image
)

def NOW():
    return datetime.now(timezone.utc).timestamp()


async def analyze_wallet(address: str) -> str:
    address = address.strip()
    chain = detect_chain(address)
    if chain == "solana":
        return await _scan_solana(address)
    elif chain == "evm":
        return await _scan_evm(address)
    return "Invalid address. Send a Solana or EVM wallet address."


async def _scan_solana(address: str) -> str:
    txs = await helius_transactions(address, limit=100)
    if not txs:
        return "No transactions found for this wallet. Make sure it is a valid Solana wallet address."

    now        = NOW()
    cutoff_7d  = now - (7  * 86400)
    cutoff_20d = now - (20 * 86400)

    trades_7d, trades_20d = [], []
    for tx in txs:
        ts = tx.get("timestamp", 0)
        has_activity = tx.get("tokenTransfers") or tx.get("nativeTransfers")
        if has_activity:
            if ts >= cutoff_7d:
                trades_7d.append(tx)
            if ts >= cutoff_20d:
                trades_20d.append(tx)

    def calc_stats(trade_list):
        total = len(trade_list)
        if total == 0:
            return 0, 0.0
        wins = sum(1 for t in trade_list if t.get("tokenTransfers"))
        return total, round(wins / total * 100, 1)

    total_7d,  wr_7d  = calc_stats(trades_7d)
    total_20d, wr_20d = calc_stats(trades_20d)

    last_ts  = txs[0].get("timestamp", 0) if txs else 0
    days_ago = days_since(last_ts) if last_ts else 999

    if days_ago <= 3:   active_tag = "Very Active"
    elif days_ago <= 7: active_tag = "Active"
    elif days_ago <= 20:active_tag = "Moderate"
    else:               active_tag = "Inactive"

    copy_rec    = "YES" if (wr_20d >= 60 and total_20d >= 5 and days_ago <= 20) else "NO"
    copy_reason = ""
    if wr_20d < 60:       copy_reason = "Win rate below 60%"
    elif total_20d < 5:   copy_reason = "Too few trades to judge"
    elif days_ago > 20:   copy_reason = "Wallet inactive over 20 days"

    ai_prompt = (
        f"You are TraceIQ. Wallet: {address} on Solana. "
        f"Last active: {days_ago} days ago. "
        f"7-day: {total_7d} trades, {wr_7d}% win rate. "
        f"20-day: {total_20d} trades, {wr_20d}% win rate. "
        f"Copy trade: {copy_rec}. "
        f"Write exactly 2 sentences. Should a trader copy this wallet? Be direct and specific."
    )
    ai = await claude_analyze(ai_prompt)

    lines = [
        "Wallet Scan - Solana",
        "---------------------",
        f"Address: {short_addr(address)}",
        f"Last Active: {days_ago} days ago ({active_tag})",
        "",
        "7-Day Performance",
        f"  Trades: {total_7d}",
        f"  Win Rate: {wr_7d}%",
        "",
        "20-Day Performance",
        f"  Trades: {total_20d}",
        f"  Win Rate: {wr_20d}%",
        "",
        f"Copy Trade: {copy_rec}",
    ]
    if copy_reason:
        lines.append(f"Reason: {copy_reason}")
    lines += ["", ai, "", f"View: solscan.io/account/{address}"]
    return "\n".join(lines)


async def _scan_evm(address: str) -> str:
    txs, chain = [], "eth"
    for c in ["eth", "bnb"]:
        t = await etherscan_txlist(address, c)
        if t:
            txs, chain = t, c
            break

    if not txs:
        return "No transactions found. Check the address and try again."

    chain_name = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer   = "etherscan.io" if chain == "eth" else "bscscan.com"
    now        = NOW()
    cutoff_7d  = now - (7  * 86400)
    cutoff_20d = now - (20 * 86400)

    txs_7d  = [t for t in txs if int(t.get("timeStamp", 0)) >= cutoff_7d]
    txs_20d = [t for t in txs if int(t.get("timeStamp", 0)) >= cutoff_20d]

    def win_rate(tx_list):
        if not tx_list:
            return 0, 0.0
        wins = sum(1 for t in tx_list if t.get("isError") == "0")
        return len(tx_list), round(wins / len(tx_list) * 100, 1)

    total_7d,  wr_7d  = win_rate(txs_7d)
    total_20d, wr_20d = win_rate(txs_20d)

    last_ts  = int(txs[0].get("timeStamp", 0))
    days_ago = days_since(last_ts)

    if days_ago <= 3:    active_tag = "Very Active"
    elif days_ago <= 7:  active_tag = "Active"
    elif days_ago <= 20: active_tag = "Moderate"
    else:                active_tag = "Inactive"

    copy_rec    = "YES" if (wr_20d >= 60 and total_20d >= 5 and days_ago <= 20) else "NO"
    copy_reason = ""
    if wr_20d < 60:     copy_reason = "Win rate below 60%"
    elif total_20d < 5: copy_reason = "Too few trades to judge"
    elif days_ago > 20: copy_reason = "Wallet inactive over 20 days"

    ai_prompt = (
        f"You are TraceIQ. Wallet: {address} on {chain_name}. "
        f"Last active: {days_ago} days ago. "
        f"7-day: {total_7d} txs, {wr_7d}% success rate. "
        f"20-day: {total_20d} txs, {wr_20d}% success rate. "
        f"Write exactly 2 sentences. Should a trader copy this wallet? Be direct."
    )
    ai = await claude_analyze(ai_prompt)

    lines = [
        f"Wallet Scan - {chain_name}",
        "---------------------",
        f"Address: {short_addr(address)}",
        f"Last Active: {days_ago} days ago ({active_tag})",
        "",
        "7-Day Performance",
        f"  Trades: {total_7d}",
        f"  Win Rate: {wr_7d}%",
        "",
        "20-Day Performance",
        f"  Trades: {total_20d}",
        f"  Win Rate: {wr_20d}%",
        "",
        f"Copy Trade: {copy_rec}",
    ]
    if copy_reason:
        lines.append(f"Reason: {copy_reason}")
    lines += ["", ai, "", f"View: {explorer}/address/{address}"]
    return "\n".join(lines)


async def analyze_pnl_image(image_bytes: bytes) -> str:
    extract_prompt = (
        "You are TraceIQ analyzing a crypto trading PNL card image. "
        "Extract every visible piece of information. "
        "Reply in this exact format (write 'unknown' if not visible):\n"
        "TOKEN: \nPROFIT: \nTIMEFRAME: \nBUY_AMOUNT: \nSELL_AMOUNT: \n"
        "TRADES: \nWALLET: \nUSERNAME: \nPLATFORM: \nOTHER: "
    )
    raw = await claude_analyze_image(image_bytes, extract_prompt)

    def extract(field):
        for line in raw.split("\n"):
            if line.strip().startswith(f"{field}:"):
                val = line.split(":", 1)[-1].strip()
                return None if val.lower() in ("unknown", "", "not visible") else val
        return None

    token     = extract("TOKEN")
    profit    = extract("PROFIT")
    timeframe = extract("TIMEFRAME")
    buy_amt   = extract("BUY_AMOUNT")
    sell_amt  = extract("SELL_AMOUNT")
    trades    = extract("TRADES")
    wallet    = extract("WALLET")
    username  = extract("USERNAME")
    platform  = extract("PLATFORM")

    lines = ["PNL Card Analysis", "---------------------"]
    if platform:  lines.append(f"Platform: {platform}")
    if username:  lines.append(f"User: {username}")
    if token:     lines.append(f"Token: {token}")
    if profit:    lines.append(f"Profit: {profit}")
    if timeframe: lines.append(f"Timeframe: {timeframe}")
    if buy_amt:   lines.append(f"Buy: {buy_amt}")
    if sell_amt:  lines.append(f"Sell: {sell_amt}")
    if trades:    lines.append(f"Trades: {trades}")
    if wallet:    lines.append(f"Wallet: {wallet}")

    if token and not wallet:
        lines.append("")
        lines.append(f"Searching for {token} on DexScreener...")
        try:
            pairs = await dexscreener_search(token)
            if pairs:
                pair  = pairs[0]
                base  = pair.get("baseToken", {})
                cid   = pair.get("chainId", "")
                ca    = base.get("address", "")
                lines += [
                    "",
                    f"Token found: {base.get('name','?')} ({base.get('symbol','?')})",
                    f"Chain: {cid}",
                    f"Contract: {ca}",
                    "",
                    "Use /top and paste the contract above to find top traders."
                ]
            else:
                lines.append("Token not found on DexScreener. Try /top with the contract address manually.")
        except Exception:
            lines.append("Could not search DexScreener automatically.")
    elif wallet:
        lines.append("")
        lines.append("Use /scan and paste the wallet address above for full analysis.")
    else:
        lines.append("")
        lines.append("Not enough info extracted. Try a clearer image or use /top with the token contract.")

    return "\n".join(lines)
