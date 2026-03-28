"""
TraceIQ — Top Wallets Module (v2)
/top → token contract → top 10 traders by activity and profitability
Uses DexScreener (free) + Helius + Etherscan
"""

import asyncio
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd,
    helius_transactions, etherscan_token_transfers,
    dexscreener_token, find_social_links, claude_analyze,
    get, HELIUS_API_KEY, HELIUS_API_BASE
)
from config import MAX_INACTIVE_DAYS, TOP_WALLET_LIMIT


async def find_top_wallets(contract: str) -> str:
    contract = contract.strip()
    chain    = detect_chain(contract)

    if chain == "solana":
        return await _top_solana(contract)
    elif chain == "evm":
        return await _top_evm(contract)
    return "Invalid contract address."


async def _top_solana(contract: str) -> str:
    dex_info = await dexscreener_token(contract)
    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown")
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???")
    price        = dex_info.get("priceUsd", "0")
    mcap         = dex_info.get("marketCap", 0)

    # Fetch recent transactions for this token mint via Helius
    try:
        data = await get(
            f"{HELIUS_API_BASE}/addresses/{contract}/transactions",
            params={"api-key": HELIUS_API_KEY, "limit": 100, "type": "SWAP"}
        )
        txs = data if isinstance(data, list) else []
    except Exception:
        txs = []

    if not txs:
        # Fallback: get token accounts (holders who interacted)
        try:
            from modules.utils import post
            data = await post(
                f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
                json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [contract, {"limit": 100}]
                }
            )
            sigs = data.get("result", [])
            txs  = [{"feePayer": s.get("memo", ""), "timestamp": s.get("blockTime", 0)} for s in sigs]
        except Exception:
            txs = []

    # Aggregate wallets from transactions
    wallet_activity = {}
    for tx in txs:
        # Get the fee payer / signer as the trader
        trader = tx.get("feePayer", "") or tx.get("accountData", [{}])[0].get("account", "") if isinstance(tx.get("accountData"), list) else ""
        if not trader or trader == contract:
            continue
        ts = tx.get("timestamp", 0)
        if trader not in wallet_activity:
            wallet_activity[trader] = {"count": 0, "last_ts": 0}
        wallet_activity[trader]["count"] += 1
        if ts > wallet_activity[trader]["last_ts"]:
            wallet_activity[trader]["last_ts"] = ts

    # Score and filter
    scored = []
    for addr, data in wallet_activity.items():
        days_ago = days_since(data["last_ts"]) if data["last_ts"] else 999
        scored.append({
            "address":  addr,
            "trades":   data["count"],
            "days_ago": days_ago,
        })

    # Sort by trade count
    scored.sort(key=lambda x: x["trades"], reverse=True)
    top = scored[:TOP_WALLET_LIMIT]

    # If still empty, try getting token largest accounts
    if not top:
        try:
            from modules.utils import post
            data = await post(
                f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
                json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getTokenLargestAccounts",
                    "params": [contract]
                }
            )
            accounts = data.get("result", {}).get("value", [])
            for acc in accounts[:10]:
                top.append({
                    "address":  acc.get("address", ""),
                    "trades":   0,
                    "days_ago": 0,
                    "amount":   acc.get("uiAmount", 0)
                })
        except Exception:
            pass

    socials = await find_social_links(contract, dex_info)

    if not top:
        return (
            f"Top Wallets - {token_symbol}\n"
            f"---------------------\n"
            f"Contract: {short_addr(contract)}\n\n"
            f"No trader data available for this token yet.\n"
            f"It may have very low volume or be too new.\n\n"
            f"Socials:\n{socials}"
        )

    lines = [
        f"Top Wallets - {token_symbol}",
        "---------------------",
        f"Token: {token_name}",
        f"Price: ${price}  MCap: {fmt_usd(mcap)}",
        f"Contract: {short_addr(contract)}",
        f"Found: {len(top)} wallets",
        "",
    ]

    for i, w in enumerate(top, 1):
        addr     = w["address"]
        days_ago = w.get("days_ago", 0)
        trades   = w.get("trades", 0)
        amount   = w.get("amount", 0)

        if days_ago <= 7:    status = "Very Active"
        elif days_ago <= 20: status = "Active"
        else:                status = "Inactive"

        lines.append(f"{i}. {short_addr(addr)}")
        if trades > 0:
            lines.append(f"   Trades: {trades}  |  {days_ago}d ago ({status})")
        elif amount > 0:
            lines.append(f"   Holdings: {amount:,.0f} tokens")
        lines.append(f"   solscan.io/account/{addr}")
        lines.append("")

    lines.append(f"Socials:\n{socials}")
    return "\n".join(lines)


async def _top_evm(contract: str) -> str:
    transfers, chain = [], "eth"
    for c in ["eth", "bnb"]:
        t = await etherscan_token_transfers(contract, c)
        if t:
            transfers, chain = t, c
            break

    dex_info     = await dexscreener_token(contract)
    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown") if dex_info else "Unknown"
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???") if dex_info else "???"
    chain_name   = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer     = "etherscan.io" if chain == "eth" else "bscscan.com"

    if not transfers:
        return (
            f"Top Wallets - {token_symbol} ({chain_name})\n"
            f"---------------------\n"
            f"No transfer data found for this contract.\n"
            f"Check the address or try a token with more activity."
        )

    # Aggregate wallets
    wallet_data = {}
    for tx in transfers:
        addr = tx.get("to", "").lower()
        if not addr or addr == contract.lower():
            continue
        ts = int(tx.get("timeStamp", 0))
        if addr not in wallet_data:
            wallet_data[addr] = {"buys": 0, "last_ts": 0}
        wallet_data[addr]["buys"] += 1
        if ts > wallet_data[addr]["last_ts"]:
            wallet_data[addr]["last_ts"] = ts

    # Score
    scored = []
    for addr, data in wallet_data.items():
        days_ago = days_since(data["last_ts"]) if data["last_ts"] else 999
        scored.append({
            "address":  addr,
            "trades":   data["buys"],
            "days_ago": days_ago,
        })

    scored.sort(key=lambda x: x["trades"], reverse=True)
    top = scored[:TOP_WALLET_LIMIT]

    socials = await find_social_links(contract, dex_info)

    lines = [
        f"Top Wallets - {token_symbol}",
        "---------------------",
        f"Token: {token_name} ({chain_name})",
        f"Contract: {short_addr(contract)}",
        f"Found: {len(top)} wallets",
        "",
    ]

    for i, w in enumerate(top, 1):
        addr     = w["address"]
        days_ago = w["days_ago"]
        trades   = w["trades"]

        if days_ago <= 7:    status = "Very Active"
        elif days_ago <= 20: status = "Active"
        else:                status = "Older"

        lines.append(f"{i}. {short_addr(addr)}")
        lines.append(f"   Trades: {trades}  |  {days_ago}d ago ({status})")
        lines.append(f"   {explorer}/address/{addr}")
        lines.append("")

    lines.append(f"Socials:\n{socials}")
    return "\n".join(lines)
