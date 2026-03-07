"""Async iNaturalist API client — adapted from inat_species.py."""

from __future__ import annotations

import httpx
import logging

from .constants import API_BASE
from .rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)

# Module-level shared client and rate limiter
_client: httpx.AsyncClient | None = None
_limiter = AsyncRateLimiter(min_interval=1.0)


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def get(endpoint: str, params: dict | None = None) -> dict:
    """Rate-limited GET request to iNat API."""
    await _limiter.acquire()
    client = await get_client()
    url = f"{API_BASE}/{endpoint}"
    resp = await client.get(url, params=params or {})
    resp.raise_for_status()
    return resp.json()


async def get_paged(
    endpoint: str, params: dict, max_results: int = 10000
) -> list[dict]:
    """Paginate through an iNat API endpoint, collecting all results."""
    results: list[dict] = []
    page = 1
    per_page = min(200, max_results)

    while len(results) < max_results:
        data = await get(endpoint, {**params, "page": page, "per_page": per_page})
        batch = data.get("results", [])
        results.extend(batch)
        total = data.get("total_results", 0)
        logger.info(f"Fetched page {page}: {len(batch)} results (total: {total})")
        if len(batch) < per_page or len(results) >= total:
            break
        page += 1

    return results[:max_results]


async def lookup_taxon(name: str, rank: str = "genus") -> dict | None:
    """Look up a taxon by name and rank."""
    data = await get("taxa", {"q": name, "rank": rank, "per_page": 5})
    results = data.get("results", [])
    if not results:
        return None

    # Prefer exact name match
    match = next(
        (t for t in results if t.get("name", "").lower() == name.lower()),
        results[0],
    )

    # Fetch full taxon details
    full = await get(f"taxa/{match['id']}", {})
    return full["results"][0] if full.get("results") else match


async def fetch_observations_by_ids(obs_ids: list[int]) -> list[dict]:
    """Fetch specific observations by their IDs (max 200 per call)."""
    if not obs_ids:
        return []

    ids_str = ",".join(str(i) for i in obs_ids)
    data = await get("observations", {"id": ids_str, "per_page": 200})
    return data.get("results", [])
