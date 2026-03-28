"""
TraceIQ — Dev Tracker Module (v2)
/dev → token contract → dev wallet analysis
Shows: previous deploys, rug history, profitability %, time since each deploy
"""

import asyncio
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd,
    helius_transactions, etherscan_contract_creator,
    etherscan_txlist, etherscan_token_transfers,
    dexscreener_token, find_social_links, claude_analyze,
    get, post, HELIUS_API_KEY, HELIUS_API_BASE,
    ETHERSCAN_BASE, ETHERSCAN_API_KEY, BSCSCAN_BASE, BSCSCAN_API_KEY
)
from config import MAX_INACTIVE_DAYS


async def analyze_dev(contract: str) -> str:
    contract = contract.strip()
    chain    = detect_chain(contract)

    if chain == "solana":
        return await _dev_solana(contract)
    elif chain == "evm":
        return await _dev_evm(contract)
    return "Invalid contract address. Please paste a token contract, not a wallet address."


# ── Solana dev ────────────────────────────────────────────────────────────────
async def _dev_solana(contract: str) -> str:
    dex_info     = await dexscreener_token(contract)
    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown") if dex_info else "Unknown"
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???") if dex_info else "???"

    # Get mint authority (dev wallet)
    try:
        data = await post(
            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getAccountInfo",
                "params": [contract, {"encoding": "jsonParsed"}]
            }
        )
        info      = data.get("result", {}).get("value", {}).get("data", {}).get("parsed", {}).get("info", {})
        dev_addr  = info.get("mintAuthority") or info.get("updateAuthority", "")
        supply    = int(info.get("supply", 0))
        decimals  = int(info.get("decimals", 6))
        actual_supply = supply / (10 ** decimals) if supply else 0
    except Exception:
        dev_addr = ""
        actual_supply = 0

    # Try to find dev from DexScreener if mint auth revoked
    if not dev_addr:
        # Check transactions to find the original deployer
        try:
            txs = await helius_transactions(contract, limit=10)
            if txs:
                # Last transaction in list is usually oldest = deployer
                dev_addr = txs[-1].get("feePayer", "")
        except Exception:
            pass

    if not dev_addr:
        return (
            f"Dev Analysis - {token_symbol}\n"
            f"---------------------\n"
            f"Could not identify deployer wallet.\n"
            f"Mint authority may be revoked (good sign).\n\n"
            f"Token: {token_name}\n"
            f"Contract: {short_addr(contract)}\n"
        )

    return await _analyze_solana_dev_wallet(dev_addr, contract, token_name, token_symbol, dex_info)


async def _analyze_solana_dev_wallet(dev_addr, contract, token_name, token_symbol, dex_info):
    # Get dev transactions
    txs = await helius_transactions(dev_addr, limit=100)

    last_ts  = txs[0].get("timestamp", 0) if txs else 0
    days_ago = days_since(last_ts) if last_ts else 999
    total_txs = len(txs)

    # Find other tokens this dev created (look for token mint instructions)
    other_tokens = []
    for tx in txs:
        for transfer in tx.get("tokenTransfers", []):
            mint = transfer.get("mint", "")
            if mint and mint != contract and mint not in [t["mint"] for t in other_tokens]:
                other_tokens.append({
                    "mint": mint,
                    "ts": tx.get("timestamp", 0)
                })

    other_tokens = other_tokens[:10]

    # Profitability: estimate from SOL transfers
    sol_received = 0
    sol_sent     = 0
    for tx in txs:
        for nt in tx.get("nativeTransfers", []):
            amt = nt.get("amount", 0) / 1e9
            if nt.get("toUserAccount") == dev_addr:
                sol_received += amt
            elif nt.get("fromUserAccount") == dev_addr:
                sol_sent += amt

    net_sol    = sol_received - sol_sent
    profit_pct = round((net_sol / sol_sent * 100), 1) if sol_sent > 0 else 0

    # Activity status
    if days_ago <= 7:    active_tag = "Very Active"
    elif days_ago <= 20: active_tag = "Active"
    else:                active_tag = "Inactive"

    # Rug risk heuristic
    rug_signals = []
    if len(other_tokens) > 5:
        rug_signals.append(f"Deployed {len(other_tokens)}+ tokens (serial launcher risk)")
    if days_ago > 30:
        rug_signals.append("Dev has been inactive for 30+ days")
    if sol_sent > sol_received * 2:
        rug_signals.append("High outbound SOL (possible liquidity drain)")

    # AI assessment
    ai_prompt = (
        f"You are TraceIQ analyzing a Solana token developer. "
        f"Token: {token_name} ({token_symbol}). "
        f"Dev wallet: {dev_addr}. "
        f"Dev last active: {days_ago} days ago. "
        f"Total transactions: {total_txs}. "
        f"Other tokens found in wallet: {len(other_tokens)}. "
        f"Net SOL flow: {net_sol:.2f} SOL. "
        f"Estimated profitability: {profit_pct}%. "
        f"Rug signals: {rug_signals if rug_signals else 'none detected'}. "
        f"Write 3 sentences max. Is this dev trustworthy? What is the risk level? Be direct and specific."
    )
    ai_summary = await claude_analyze(ai_prompt)
    socials    = await find_social_links(contract, dex_info)

    lines = [
        f"Dev Analysis - {token_symbol}",
        "---------------------",
        f"Token: {token_name}",
        f"Contract: {short_addr(contract)}",
        "",
        "Developer Wallet",
        f"Address: {dev_addr}",
        f"Last Active: {days_ago} days ago ({active_tag})",
        f"Total Txs: {total_txs}",
        f"Profitability: {profit_pct}%",
        f"Other Tokens Deployed: {len(other_tokens)}",
        "",
    ]

    if other_tokens:
        lines.append("Previous Deploys:")
        for i, t in enumerate(other_tokens[:5], 1):
            d = days_since(t["ts"]) if t["ts"] else "?"
            lines.append(f"  {i}. {short_addr(t['mint'])}  ({d}d ago)")
            lines.append(f"     solscan.io/token/{t['mint']}")
        lines.append("")

    if rug_signals:
        lines.append("Risk Flags:")
        for r in rug_signals:
            lines.append(f"  - {r}")
        lines.append("")
    else:
        lines.append("Risk Flags: None detected")
        lines.append("")

    lines += [
        "AI Assessment:",
        ai_summary,
        "",
        f"View Dev: solscan.io/account/{dev_addr}",
        "",
        f"Socials:\n{socials}"
    ]
    return "\n".join(lines)


# ── EVM dev ───────────────────────────────────────────────────────────────────
async def _dev_evm(contract: str) -> str:
    dev_addr, chain = "", "eth"
    for c in ["eth", "bnb"]:
        addr = await etherscan_contract_creator(contract, c)
        if addr:
            dev_addr, chain = addr, c
            break

    dex_info     = await dexscreener_token(contract)
    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown") if dex_info else "Unknown"
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???") if dex_info else "???"
    chain_name   = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer     = "etherscan.io" if chain == "eth" else "bscscan.com"
    base_url     = ETHERSCAN_BASE if chain == "eth" else BSCSCAN_BASE
    api_key      = ETHERSCAN_API_KEY if chain == "eth" else BSCSCAN_API_KEY

    if not dev_addr:
        return (
            f"Dev Analysis - {token_symbol}\n"
            f"---------------------\n"
            f"Could not find deployer wallet.\n"
            f"Check the contract address is correct."
        )

    # Get dev transactions
    dev_txs = await etherscan_txlist(dev_addr, chain)

    last_ts   = int(dev_txs[0].get("timeStamp", 0)) if dev_txs else 0
    days_ago  = days_since(last_ts) if last_ts else 999
    total_txs = len(dev_txs)

    # Find other contracts deployed by this dev
    prev_deploys = []
    for tx in dev_txs:
        ca = tx.get("contractAddress", "")
        if ca and ca.lower() != contract.lower():
            ts = int(tx.get("timeStamp", 0))
            prev_deploys.append({"address": ca, "ts": ts})

    prev_deploys = prev_deploys[:10]

    # Profitability: ETH/BNB in vs out
    eth_in  = sum(int(t.get("value", 0)) for t in dev_txs if t.get("to", "").lower() == dev_addr.lower())
    eth_out = sum(int(t.get("value", 0)) for t in dev_txs if t.get("from", "").lower() == dev_addr.lower())
    net_eth = (eth_in - eth_out) / 1e18
    profit_pct = round((net_eth / (eth_out / 1e18) * 100), 1) if eth_out > 0 else 0

    if days_ago <= 7:    active_tag = "Very Active"
    elif days_ago <= 20: active_tag = "Active"
    else:                active_tag = "Inactive"

    # Rug signals
    rug_signals = []
    if len(prev_deploys) > 5:
        rug_signals.append(f"Deployed {len(prev_deploys)}+ contracts (serial launcher)")
    if days_ago > 30:
        rug_signals.append("Dev inactive for 30+ days")
    if eth_out > eth_in * 2:
        rug_signals.append("High outbound ETH/BNB (possible drain)")

    # Check each previous deploy for rug patterns via DexScreener
    rug_count = 0
    for d in prev_deploys[:5]:
        try:
            info = await dexscreener_token(d["address"])
            if info:
                liq = float(info.get("liquidity", {}).get("usd", 0))
                if liq < 100:
                    rug_count += 1
        except Exception:
            pass

    if rug_count > 0:
        rug_signals.append(f"{rug_count} previous token(s) have near-zero liquidity (likely rugged)")

    ai_prompt = (
        f"You are TraceIQ analyzing a {chain_name} token developer. "
        f"Token: {token_name} ({token_symbol}). "
        f"Dev wallet: {dev_addr}. "
        f"Last active: {days_ago} days ago. "
        f"Total transactions: {total_txs}. "
        f"Previous contracts deployed: {len(prev_deploys)}. "
        f"Estimated profitability: {profit_pct}%. "
        f"Rug signals: {rug_signals if rug_signals else 'none'}. "
        f"Tokens with near-zero liquidity: {rug_count}. "
        f"Write 3 sentences. Is this dev trustworthy? What is the risk? Be direct."
    )
    ai_summary, socials = await asyncio.gather(
        claude_analyze(ai_prompt),
        find_social_links(contract, dex_info)
    )

    lines = [
        f"Dev Analysis - {token_symbol}",
        "---------------------",
        f"Token: {token_name} ({chain_name})",
        f"Contract: {short_addr(contract)}",
        "",
        "Developer Wallet",
        f"Address: {dev_addr}",
        f"Last Active: {days_ago} days ago ({active_tag})",
        f"Total Txs: {total_txs}",
        f"Profitability: {profit_pct}%",
        f"Previous Deploys: {len(prev_deploys)}",
        f"Suspected Rugs: {rug_count}",
        "",
    ]

    if prev_deploys:
        lines.append("Previous Tokens Deployed:")
        for i, d in enumerate(prev_deploys[:5], 1):
            age = days_since(d["ts"]) if d["ts"] else "?"
            lines.append(f"  {i}. {short_addr(d['address'])}  ({age} days ago)")
            lines.append(f"     {explorer}/address/{d['address']}")
        lines.append("")

    if rug_signals:
        lines.append("Risk Flags:")
        for r in rug_signals:
            lines.append(f"  - {r}")
        lines.append("")
    else:
        lines.append("Risk Flags: None detected")
        lines.append("")

    lines += [
        "AI Assessment:",
        ai_summary,
        "",
        f"View Dev: {explorer}/address/{dev_addr}",
        "",
        f"Socials:\n{socials}"
    ]
    return "\n".join(lines)
