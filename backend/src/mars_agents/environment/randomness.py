"""Independent deterministic streams; process hash seeds and iteration order do not matter."""

import hashlib
import json

import numpy as np


def seeded_rng(seed: int, stream: str, *keys: str | int) -> np.random.Generator:
    payload = json.dumps([seed, stream, *keys], separators=(",", ":")).encode()
    entropy = int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")
    return np.random.default_rng(entropy)


def tie_key(seed: int, round_number: int, agent_id: str) -> bytes:
    payload = json.dumps([seed, "discovery_tie", round_number, agent_id]).encode()
    return hashlib.sha256(payload).digest()
