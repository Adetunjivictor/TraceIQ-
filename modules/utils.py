"""
TraceIQ — Shared Utilities
Chain detection, HTTP helpers, Claude AI, social linking
"""

import re
import base64
import asyncio
import httpx
import anthropic
from datetime import datetime, timezone
from config import (
    ANTHROPIC_API_KEY, HELIUS_API_KEY, BIRDEYE_API_KEY,
    ETHERSCAN_API_KEY, BSCSCAN_API_KEY,
    HELIUS_API_BASE, BIRDEYE_BASE, ETHERSCAN_BASE,
    BSCSCAN_BASE, DEXSCREENER_BASE
)

# ── Claude client ─────────────────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Chain Detection ───────────────────────────────────────────────────────────
def detect_chain(address: str) -> str:
    """Detect blockchain from address format."""
    address = address.strip()
    if re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address):
        return "solana"
    elif re.match(r'^0x[a-fA-F0-9]{40}$', address):
        return "evm"  # ETH or BNB — we'll check both
    return "unknown"


def detect_evm_chain(address: str) -> str:
    """Try to determine if EVM address is ETH or BNB based on context."""
    return "eth"  # default; caller can override


# ── Days since timestamp ──────────────────────────────────────────────────────
def days_since(timestamp: int) -> int:
    """Return days since a unix timestamp."""
    now = datetime.now(timezone.utc).timestamp()
    return int((now - timestamp) / 86400)


# ── HTTP helper ───────────────────────────────────────────────────────────────
async def get(url: str, params: dict = None, headers: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers or {})
        r.raise_for_status()
        return r.json()


async def post(url: str, json: dict = None, headers: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=json, headers=headers or {})
        r.raise_for_status()
        return r.json()


# ── DexScreener ───────────────────────────────────────────────────────────────
async def dexscreener_token(contract: str) -> dict:
    """Get token info from DexScreener (free, no key needed)."""
    try:
        data = await get(f"{DEXSCREENER_BASE}/dex/tokens/{contract}")
        pairs = data.get("pairs", [])
        if pairs:
            return pairs[0]
    except Exception:
        pass
    return {}


async def dexscreener_search(query: str) -> list:
    try:
        data = await get(f"{DEXSCREENER_BASE}/dex/search", params={"q": query})
        return data.get("pairs", [])
    except Exception:
        return []


# ── Helius (Solana) ───────────────────────────────────────────────────────────
async def helius_transactions(address: str, limit: int = 100) -> list:
    """Get recent transactions for a Solana address."""
    try:
        data = await get(
            f"{HELIUS_API_BASE}/addresses/{address}/transactions",
            params={"api-key": HELIUS_API_KEY, "limit": limit}
        )
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def helius_token_holders(mint: str) -> list:
    """Get token holders via Helius."""
    try:
        data = await post(
            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint]
            }
        )
        return data.get("result", {}).get("value", [])
    except Exception:
        return []


async def helius_wallet_tokens(address: str) -> list:
    """Get token balances for a Solana wallet."""
    try:
        data = await post(
            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ]
            }
        )
        return data.get("result", {}).get("value", [])
    except Exception:
        return []


# ── Birdeye (Solana trading data) ─────────────────────────────────────────────
async def birdeye_wallet_pnl(address: str) -> dict:
    """Get wallet PNL data from Birdeye."""
    try:
        headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
        data = await get(
            f"{BIRDEYE_BASE}/v1/wallet/token_list",
            params={"wallet": address},
            headers=headers
        )
        return data.get("data", {})
    except Exception:
        return {}


async def birdeye_token_traders(contract: str) -> list:
    """Get top traders for a token on Birdeye."""
    try:
        headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
        data = await get(
            f"{BIRDEYE_BASE}/defi/v2/tokens/top_traders",
            params={"address": contract, "time_frame": "30D", "sort_type": "desc", "sort_by": "volume", "limit": 50},
            headers=headers
        )
        return data.get("data", {}).get("items", [])
    except Exception:
        return []


async def birdeye_token_info(contract: str) -> dict:
    """Get token overview from Birdeye."""
    try:
        headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
        data = await get(
            f"{BIRDEYE_BASE}/defi/token_overview",
            params={"address": contract},
            headers=headers
        )
        return data.get("data", {})
    except Exception:
        return {}


# ── Etherscan ─────────────────────────────────────────────────────────────────
async def etherscan_txlist(address: str, chain: str = "eth") -> list:
    base = ETHERSCAN_BASE if chain == "eth" else BSCSCAN_BASE
    key  = ETHERSCAN_API_KEY if chain == "eth" else BSCSCAN_API_KEY
    try:
        data = await get(base, params={
            "module": "account", "action": "txlist",
            "address": address, "sort": "desc",
            "page": 1, "offset": 100, "apikey": key
        })
        return data.get("result", []) if data.get("status") == "1" else []
    except Exception:
        return []


async def etherscan_contract_creator(contract: str, chain: str = "eth") -> str:
    """Get the deployer address of a contract."""
    base = ETHERSCAN_BASE if chain == "eth" else BSCSCAN_BASE
    key  = ETHERSCAN_API_KEY if chain == "eth" else BSCSCAN_API_KEY
    try:
        data = await get(base, params={
            "module": "contract", "action": "getcontractcreation",
            "contractaddresses": contract, "apikey": key
        })
        results = data.get("result", [])
        if results:
            return results[0].get("contractCreator", "")
    except Exception:
        pass
    return ""


async def etherscan_token_transfers(contract: str, chain: str = "eth") -> list:
    """Get token transfer events for a contract."""
    base = ETHERSCAN_BASE if chain == "eth" else BSCSCAN_BASE
    key  = ETHERSCAN_API_KEY if chain == "eth" else BSCSCAN_API_KEY
    try:
        data = await get(base, params={
            "module": "account", "action": "tokentx",
            "contractaddress": contract, "sort": "desc",
            "page": 1, "offset": 200, "apikey": key
        })
        return data.get("result", []) if data.get("status") == "1" else []
    except Exception:
        return []


# ── Social Link Finder ────────────────────────────────────────────────────────
async def find_social_links(address: str, token_info: dict = None) -> str:
    """Attempt to find social links associated with a wallet or token."""
    links = []

    # From token info (DexScreener often has socials)
    if token_info:
        info = token_info.get("info", {})
        socials = info.get("socials", [])
        websites = info.get("websites", [])

        for s in socials:
            stype = s.get("type", "").lower()
            url   = s.get("url", "")
            if url:
                if "twitter" in stype or "x.com" in url:
                    links.append(f"🐦 Twitter: {url}")
                elif "telegram" in stype:
                    links.append(f"✈️ Telegram: {url}")
                elif "discord" in stype:
                    links.append(f"💬 Discord: {url}")
                elif "reddit" in stype:
                    links.append(f"🔴 Reddit: {url}")
                elif "github" in stype:
                    links.append(f"🐙 GitHub: {url}")
                else:
                    links.append(f"🔗 {stype.title()}: {url}")

        for w in websites:
            url = w.get("url", "")
            if url:
                links.append(f"🌐 Website: {url}")

    if links:
        return "\n".join(links)
    return "_No social links found_"


# ── Claude AI helpers ─────────────────────────────────────────────────────────
async def claude_analyze(prompt: str) -> str:
    """Call Claude for text analysis."""
    try:
        msg = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        return f"AI analysis unavailable: {str(e)}"


async def claude_analyze_image(image_bytes: bytes, prompt: str) -> str:
    """Call Claude vision to analyze an image."""
    try:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        msg = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        return msg.content[0].text
    except Exception as e:
        return f"Image analysis unavailable: {str(e)}"


# ── Format helpers ────────────────────────────────────────────────────────────
def short_addr(addr: str) -> str:
    """Shorten address for display."""
    if len(addr) > 12:
        return f"{addr[:6]}...{addr[-4:]}"
    return addr


def fmt_usd(val) -> str:
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v/1_000_000:.2f}M"
        elif v >= 1_000:
            return f"${v/1_000:.1f}K"
        return f"${v:.2f}"
    except Exception:
        return "$0"


def fmt_pct(val) -> str:
    try:
        return f"{float(val)*100:.1f}%"
    except Exception:
        return "N/A"
