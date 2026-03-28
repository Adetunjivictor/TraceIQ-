"""
TraceIQ — Top Wallets Module
/top → paste contract → find 80-100% win rate wallets active 7-20 days
"""

import asyncio
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd, fmt_pct,
    birdeye_token_traders, birdeye_token_info,
    etherscan_token_transfers, etherscan_txlist,
    dexscreener_token, find_social_links,
    claude_analyze
)
from config import MIN_WIN_RATE, MAX_INACTIVE_DAYS, MIN_TRADES, TOP_WALLET_LIMIT


async def find_top_wallets(contract: str) -> str:
    contract = contract.strip()
    chain    = detect_chain(contract)

    if chain == "solana":
        return await _top_solana(contract)
    elif chain == "evm":
        return await _top_evm(contract)
    else:
        return "❌ Invalid contract address. Please paste a valid Solana or EVM token contract."


# ── Solana top wallets ────────────────────────────────────────────────────────
async def _top_solana(contract: str) -> str:
    # Fetch token info and traders in parallel
    token_info, traders, dex_info = await asyncio.gather(
        birdeye_token_info(contract),
        birdeye_token_traders(contract),
        dexscreener_token(contract)
    )

    token_name   = token_info.get("name", "Unknown Token")
    token_symbol = token_info.get("symbol", "???")
    price        = token_info.get("price", 0)
    mcap         = token_info.get("realMc", token_info.get("mc", 0))

    if not traders:
        return (
            f"❌ No trader data found for `{short_addr(contract)}`\n\n"
            "This token may be too new, have low volume, or not indexed yet on Birdeye."
        )

    # Filter traders
    qualified = []
    for t in traders:
        win_rate  = float(t.get("winRate", 0))
        last_time = int(t.get("lastTradeUnixTime", 0))
        trade_cnt = int(t.get("tradeCount", t.get("numTrade", 0)))
        days_ago  = days_since(last_time) if last_time else 999

        if (
            win_rate >= MIN_WIN_RATE and
            days_ago <= MAX_INACTIVE_DAYS and
            trade_cnt >= MIN_TRADES
        ):
            qualified.append({
                "address":   t.get("address", ""),
                "win_rate":  win_rate,
                "days_ago":  days_ago,
                "trades":    trade_cnt,
                "pnl":       float(t.get("pnl", t.get("realizedPnl", 0))),
                "volume":    float(t.get("volume", 0)),
            })

    # Sort by win rate desc
    qualified.sort(key=lambda x: x["win_rate"], reverse=True)
    qualified = qualified[:TOP_WALLET_LIMIT]

    if not qualified:
        return (
            f"⚠️ No wallets found matching:\n"
            f"• Win rate ≥ {int(MIN_WIN_RATE*100)}%\n"
            f"• Active within {MAX_INACTIVE_DAYS} days\n"
            f"• Min {MIN_TRADES} trades\n\n"
            f"Try a token with more trading history."
        )

    # Social links from DexScreener
    socials = await find_social_links(contract, dex_info)

    # Build message
    msg = (
        f"🏆 *Top Wallets — {token_symbol}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 {token_name} | {fmt_usd(price)} | MCap: {fmt_usd(mcap)}\n"
        f"📍 `{contract}`\n"
        f"✅ Found {len(qualified)} qualifying wallets\n\n"
    )

    for i, w in enumerate(qualified, 1):
        addr      = w["address"]
        win_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        active    = "🟢" if w["days_ago"] <= 7 else "🟡"

        msg += (
            f"{win_emoji} `{short_addr(addr)}`\n"
            f"   🎯 Win Rate: *{w['win_rate']*100:.1f}%*  {active} {w['days_ago']}d ago\n"
            f"   📊 Trades: {w['trades']}  💰 PNL: {fmt_usd(w['pnl'])}\n"
            f"   🔗 [Solscan](https://solscan.io/account/{addr})\n\n"
        )

    msg += f"*Socials:*\n{socials}"
    return msg


# ── EVM top wallets ───────────────────────────────────────────────────────────
async def _top_evm(contract: str) -> str:
    # Try ETH first, then BNB
    for chain in ["eth", "bnb"]:
        transfers, dex_info = await asyncio.gather(
            etherscan_token_transfers(contract, chain),
            dexscreener_token(contract)
        )

        if transfers:
            return await _process_evm_transfers(contract, transfers, dex_info, chain)

    return "❌ No transfer data found. Check the contract address or try a different chain."


async def _process_evm_transfers(contract, transfers, dex_info, chain) -> str:
    chain_name = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer   = "etherscan.io" if chain == "eth" else "bscscan.com"
    token_name = transfers[0].get("tokenName", "Unknown") if transfers else "Unknown"
    token_sym  = transfers[0].get("tokenSymbol", "???") if transfers else "???"

    # Aggregate wallet activity
    wallet_data = {}
    for tx in transfers:
        addr = tx.get("to", "").lower()
        if not addr or addr == contract.lower():
            continue
        ts = int(tx.get("timeStamp", 0))
        if addr not in wallet_data:
            wallet_data[addr] = {"buys": 0, "sells": 0, "last_ts": 0, "txs": []}
        wallet_data[addr]["txs"].append(tx)
        if ts > wallet_data[addr]["last_ts"]:
            wallet_data[addr]["last_ts"] = ts

    # Basic win rate estimation: wallets that bought and sold (completed trades)
    qualified = []
    for addr, data in wallet_data.items():
        days_ago = days_since(data["last_ts"]) if data["last_ts"] else 999
        tx_count = len(data["txs"])

        if days_ago <= MAX_INACTIVE_DAYS and tx_count >= MIN_TRADES:
            qualified.append({
                "address":  addr,
                "days_ago": days_ago,
                "trades":   tx_count,
            })

    # Sort by trade count (proxy for activity)
    qualified.sort(key=lambda x: x["trades"], reverse=True)
    qualified = qualified[:TOP_WALLET_LIMIT]

    if not qualified:
        return (
            f"⚠️ No active wallets found matching criteria for this {chain_name} token.\n"
            f"Try a token with more trading history."
        )

    socials = await find_social_links(contract, dex_info)

    msg = (
        f"🏆 *Top Wallets — {token_sym}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 {token_name} ({chain_name})\n"
        f"📍 `{contract}`\n"
        f"✅ Found {len(qualified)} active wallets\n\n"
    )

    for i, w in enumerate(qualified, 1):
        addr      = w["address"]
        win_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        active    = "🟢" if w["days_ago"] <= 7 else "🟡"

        msg += (
            f"{win_emoji} `{short_addr(addr)}`\n"
            f"   {active} Active {w['days_ago']}d ago  📊 {w['trades']} txs\n"
            f"   🔗 [{explorer}](https://{explorer}/address/{addr})\n\n"
        )

    msg += f"*Socials:*\n{socials}"
    return msg
