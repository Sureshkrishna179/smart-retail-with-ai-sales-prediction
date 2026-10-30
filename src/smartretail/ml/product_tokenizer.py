"""
SmartRetail AI — Product Tokenizer (Two-Way ID ↔ Name Mapper)
==============================================================
Privacy-first deterministic encoder/decoder for uploaded datasets.

Flow:
  1. ENCODE: User's raw product names → clean internal IDs (P001, P002, ...)
  2. ML trains and predicts using clean IDs internally
  3. DECODE: Internal IDs → user's original product names for display

Zero external API calls. Zero data leakage. O(1) lookup time.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ProductTokenizer:
    """Bidirectional product name ↔ surrogate ID mapper.

    Thread-safe for reads after initial encoding (dict lookups are atomic
    in CPython). A new encode() call replaces both maps atomically.
    """

    def __init__(self, prefix: str = "P") -> None:
        self._prefix = prefix
        # Forward map: original name → surrogate ID
        self._name_to_id: dict[str, str] = {}
        # Reverse map: surrogate ID → original name
        self._id_to_name: dict[str, str] = {}

    # ── Encoding (raw names → IDs) ──────────────────────────────────────

    def encode(self, product_names: list[str]) -> dict[str, str]:
        """Build bidirectional maps from a list of unique product names.

        Args:
            product_names: List of raw product names from the uploaded CSV.

        Returns:
            dict mapping each original name to its surrogate ID.
        """
        name_to_id: dict[str, str] = {}
        id_to_name: dict[str, str] = {}

        for idx, name in enumerate(sorted(set(product_names)), start=1):
            surrogate = f"{self._prefix}{idx:03d}"
            name_to_id[name] = surrogate
            id_to_name[surrogate] = name

        # Atomic swap — both maps are consistent at all times
        self._name_to_id = name_to_id
        self._id_to_name = id_to_name

        logger.info(
            "ProductTokenizer encoded %d products (%s → %s ... %s → %s)",
            len(name_to_id),
            list(name_to_id.keys())[0] if name_to_id else "N/A",
            list(name_to_id.values())[0] if name_to_id else "N/A",
            list(name_to_id.keys())[-1] if name_to_id else "N/A",
            list(name_to_id.values())[-1] if name_to_id else "N/A",
        )
        return dict(name_to_id)

    # ── Decoding (IDs → names) ──────────────────────────────────────────

    def decode(self, surrogate_id: str) -> str:
        """Translate a surrogate ID back to the original product name.

        Returns the original name, or the surrogate_id itself if not found.
        """
        return self._id_to_name.get(surrogate_id, surrogate_id)

    def decode_dict(self, data: dict[str, float]) -> dict[str, float]:
        """Decode all keys in a {surrogate_id: value} dict back to names."""
        return {self.decode(k): v for k, v in data.items()}

    # ── Lookup helpers ──────────────────────────────────────────────────

    def get_id(self, name: str) -> Optional[str]:
        """Get the surrogate ID for a product name, or None."""
        return self._name_to_id.get(name)

    def get_name(self, surrogate_id: str) -> Optional[str]:
        """Get the original name for a surrogate ID, or None."""
        return self._id_to_name.get(surrogate_id)

    def has_products(self) -> bool:
        """Return True if the tokenizer has any encoded products."""
        return len(self._name_to_id) > 0

    def get_all_names(self) -> list[str]:
        """Return all original product names in sorted order."""
        return sorted(self._name_to_id.keys())

    def get_all_ids(self) -> list[str]:
        """Return all surrogate IDs in sorted order."""
        return sorted(self._id_to_name.keys())

    def get_name_to_id_map(self) -> dict[str, str]:
        """Return a copy of the full name → ID mapping."""
        return dict(self._name_to_id)

    def get_id_to_name_map(self) -> dict[str, str]:
        """Return a copy of the full ID → name mapping."""
        return dict(self._id_to_name)

    def clear(self) -> None:
        """Reset the tokenizer (e.g., when switching datasets)."""
        self._name_to_id = {}
        self._id_to_name = {}

    def __len__(self) -> int:
        return len(self._name_to_id)

    def __repr__(self) -> str:
        return f"ProductTokenizer(prefix={self._prefix!r}, products={len(self)})"

