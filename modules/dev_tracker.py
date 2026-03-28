"""
TraceIQ — Dev Wallet Tracker Module
/dev → paste contract → analyze deployer wallet + flag risks
"""

import asyncio
from modules.utils import (
    detect_chain, days_since, short_addr, fmt_usd,
    helius_transactions, etherscan_contract_creator,
    etherscan_txlist, dexscreener_token,
    find_social_links, claude_analyze
)
from config import MAX_INACTIVE_DAYS


async def analyze_dev(contract: str) -> str:
    contract = contract.strip()
    chain    = detect_chain(contract)

    if chain == "solana":
        return await _dev_solana(contract)
    elif chain == "evm":
        return await _dev_evm(contract)
    else:
        return "❌ Invalid contract address."


# ── Solana dev analysis ───────────────────────────────────────────────────────
async def _dev_solana(contract: str) -> str:
    # On Solana, the mint authority is effectively the "dev"
    # We use Helius to get mint account info
    from modules.utils import post, HELIUS_API_KEY

    try:
        data = await post(
            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getAccountInfo",
                "params": [contract, {"encoding": "jsonParsed"}]
            }
        )
        account_info = data.get("result", {}).get("value", {})
        parsed       = account_info.get("data", {}).get("parsed", {})
        info         = parsed.get("info", {})
        mint_auth    = info.get("mintAuthority", None)
        freeze_auth  = info.get("freezeAuthority", None)
        supply       = int(info.get("supply", 0))
        decimals     = int(info.get("decimals", 6))
        actual_supply = supply / (10 ** decimals)
    except Exception:
        mint_auth = None
        freeze_auth = None
        actual_supply = 0

    dex_info = await dexscreener_token(contract)
    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown")
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???")

    if not mint_auth:
        # Mint authority revoked — good sign
        msg = (
            f"🧑‍💻 *Dev Analysis — {token_symbol}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 {token_name}\n"
            f"📍 `{contract}`\n\n"
            f"✅ *Mint authority: REVOKED*\n"
            f"Dev cannot mint new tokens. This is a positive safety signal.\n\n"
        )
        if freeze_auth:
            msg += f"⚠️ Freeze authority still active: `{short_addr(freeze_auth)}`\n\n"
        else:
            msg += f"✅ Freeze authority: REVOKED\n\n"

        socials = await find_social_links(contract, dex_info)
        msg += f"*Socials:*\n{socials}"
        return msg

    # Analyze mint authority wallet
    dev_addr = mint_auth
    txs      = await helius_transactions(dev_addr, limit=50)

    last_ts  = txs[0].get("timestamp", 0) if txs else 0
    days_ago = days_since(last_ts) if last_ts else 999

    if days_ago <= 7:
        active_tag = "🟢 Very Active"
    elif days_ago <= MAX_INACTIVE_DAYS:
        active_tag = "🟡 Active"
    else:
        active_tag = "🔴 Inactive (>20 days)"

    total_txs = len(txs)

    # Risk flags
    flags = []
    if freeze_auth:
        flags.append("⚠️ Freeze authority active — dev can freeze wallets")
    if days_ago > MAX_INACTIVE_DAYS:
        flags.append("⚠️ Dev inactive for 20+ days — potential abandon risk")
    if total_txs < 5:
        flags.append("⚠️ Very few transactions — new or fresh wallet")

    # AI risk assessment
    ai_prompt = f"""You are TraceIQ, a crypto wallet intelligence bot analyzing a token deployer.

Token: {token_name} ({token_symbol}) on Solana
Dev wallet: {dev_addr}
Last active: {days_ago} days ago
Recent transactions: {total_txs}
Mint authority: ACTIVE (dev can still mint tokens)
Freeze authority: {"ACTIVE" if freeze_auth else "revoked"}
Supply: {actual_supply:,.0f} tokens

Give a 2-3 sentence risk assessment of this developer. Be direct and useful for a crypto trader deciding whether to buy this token."""

    ai_summary = await claude_analyze(ai_prompt)
    socials    = await find_social_links(contract, dex_info)

    msg = (
        f"🧑‍💻 *Dev Analysis — {token_symbol}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 {token_name} | Solana\n"
        f"📍 Contract: `{short_addr(contract)}`\n\n"
        f"*Deployer Wallet:*\n"
        f"📍 `{dev_addr}`\n"
        f"📅 Last Active: {days_ago}d ago  {active_tag}\n"
        f"📊 Recent Txs: {total_txs}\n"
        f"🔑 Mint Auth: ⚠️ ACTIVE\n"
        f"❄️ Freeze Auth: {'⚠️ ACTIVE' if freeze_auth else '✅ Revoked'}\n\n"
    )

    if flags:
        msg += "*⚠️ Risk Flags:*\n"
        for f in flags:
            msg += f"{f}\n"
        msg += "\n"

    msg += f"*🤖 AI Risk Assessment:*\n_{ai_summary}_\n\n"
    msg += f"🔗 [View Dev on Solscan](https://solscan.io/account/{dev_addr})\n\n"
    msg += f"*Socials:*\n{socials}"

    return msg


# ── EVM dev analysis ──────────────────────────────────────────────────────────
async def _dev_evm(contract: str) -> str:
    # Try ETH then BNB
    for chain in ["eth", "bnb"]:
        dev_addr = await etherscan_contract_creator(contract, chain)
        if dev_addr:
            return await _analyze_evm_dev(contract, dev_addr, chain)

    return "❌ Could not find deployer wallet. Check the contract address."


async def _analyze_evm_dev(contract: str, dev_addr: str, chain: str) -> str:
    chain_name = "Ethereum" if chain == "eth" else "BNB Chain"
    explorer   = "etherscan.io" if chain == "eth" else "bscscan.com"

    dev_txs, dex_info = await asyncio.gather(
        etherscan_txlist(dev_addr, chain),
        dexscreener_token(contract)
    )

    token_name   = dex_info.get("baseToken", {}).get("name", "Unknown")
    token_symbol = dex_info.get("baseToken", {}).get("symbol", "???")

    last_ts  = int(dev_txs[0].get("timeStamp", 0)) if dev_txs else 0
    days_ago = days_since(last_ts) if last_ts else 999
    total_txs = len(dev_txs)

    if days_ago <= 7:
        active_tag = "🟢 Very Active"
    elif days_ago <= MAX_INACTIVE_DAYS:
        active_tag = "🟡 Active"
    else:
        active_tag = "🔴 Inactive"

    # Count unique contracts deployed by this dev
    contracts_deployed = set(
        tx.get("contractAddress", "") for tx in dev_txs
        if tx.get("contractAddress")
    )

    # Risk flags
    flags = []
    if days_ago > MAX_INACTIVE_DAYS:
        flags.append("⚠️ Dev inactive for 20+ days")
    if len(contracts_deployed) > 5:
        flags.append(f"⚠️ Dev deployed {len(contracts_deployed)} contracts — serial launcher risk")
    if total_txs < 5:
        flags.append("⚠️ Very few transactions — fresh wallet")

    # AI assessment
    ai_prompt = f"""You are TraceIQ, a crypto wallet intelligence bot analyzing a token deployer.

Token: {token_name} ({token_symbol}) on {chain_name}
Dev wallet: {dev_addr}
Last active: {days_ago} days ago
Recent transactions: {total_txs}
Other contracts deployed by this wallet: {len(contracts_deployed)}

Give a 2-3 sentence risk assessment of this developer. Be direct and useful for a crypto trader."""

    ai_summary, socials = await asyncio.gather(
        claude_analyze(ai_prompt),
        find_social_links(contract, dex_info)
    )

    msg = (
        f"🧑‍💻 *Dev Analysis — {token_symbol}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 {token_name} | {chain_name}\n"
        f"📍 Contract: `{short_addr(contract)}`\n\n"
        f"*Deployer Wallet:*\n"
        f"📍 `{dev_addr}`\n"
        f"📅 Last Active: {days_ago}d ago  {active_tag}\n"
        f"📊 Recent Txs: {total_txs}\n"
        f"🏭 Contracts Deployed: {len(contracts_deployed)}\n\n"
    )

    if flags:
        msg += "*⚠️ Risk Flags:*\n"
        for f in flags:
            msg += f"{f}\n"
        msg += "\n"

    msg += f"*🤖 AI Risk Assessment:*\n_{ai_summary}_\n\n"
    msg += f"🔗 [View Dev on {explorer}](https://{explorer}/address/{dev_addr})\n\n"
    msg += f"*Socials:*\n{socials}"

    return msg
