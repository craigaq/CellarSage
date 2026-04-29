"""
Apify scrape manager.
Triggers an Actor run, polls until completion, and returns the dataset items.
"""

import os
import logging
import time
from typing import Any

from apify_client import ApifyClient

log = logging.getLogger(__name__)

# Max seconds to wait for a single actor run before giving up.
RUN_TIMEOUT_SECONDS = 600


def _client() -> ApifyClient:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise EnvironmentError("APIFY_API_TOKEN environment variable not set")
    return ApifyClient(token)


def run_actor(actor_id: str, actor_input: dict, max_items: int) -> list[dict]:
    """
    Start an Apify Actor, wait for it to finish, and return the dataset rows.

    Args:
        actor_id:    Apify actor identifier, e.g. 'dromb/liquorland-au-...'
        actor_input: Input dict merged with max_items limit.
        max_items:   Hard cap — keeps runs within the free-tier quota.

    Returns:
        List of raw item dicts from the actor's default dataset.
    """
    client = _client()

    run_input = {**actor_input, "maxItems": max_items}
    log.info("Starting actor %s (maxItems=%d) …", actor_id, max_items)

    run = client.actor(actor_id).call(run_input=run_input, timeout_secs=RUN_TIMEOUT_SECONDS)

    status = run.get("status", "UNKNOWN")
    run_id = run.get("id", "?")
    log.info("Actor %s run %s finished with status: %s", actor_id, run_id, status)

    if status != "SUCCEEDED":
        raise RuntimeError(
            f"Actor {actor_id!r} run {run_id} did not succeed — status: {status!r}. "
            "Check the Apify Console for logs."
        )

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(f"Actor run {run_id} returned no defaultDatasetId")

    items: list[dict] = list(
        client.dataset(dataset_id).iterate_items(limit=max_items)
    )

    # Flatten nested lists — some actors return [[item, item], [item]]
    flat: list[dict] = []
    for entry in items:
        if isinstance(entry, list):
            flat.extend(entry)
        elif isinstance(entry, dict):
            flat.append(entry)

    log.info("Fetched %d items from dataset %s", len(flat), dataset_id)
    return flat
