from __future__ import annotations

from math import sqrt
from typing import Mapping, Sequence


def cosine_similarity_binary_weighted(
    *,
    product_tag_ids: Sequence[int],
    user_tag_weights: Mapping[int, int],
) -> float:
    """
    Cosine similarity between a weighted user tag vector and a binary product tag vector.

    user vector: w_t
    product vector: x_t in {0,1}
    cosine = dot(w, x) / (||w|| * ||x||)
    """
    if not product_tag_ids or not user_tag_weights:
        return 0.0

    # dot
    dot = 0.0
    for tid in product_tag_ids:
        dot += float(user_tag_weights.get(int(tid), 0))
    if dot <= 0:
        return 0.0

    # norms
    w_norm_sq = 0.0
    for w in user_tag_weights.values():
        w_norm_sq += float(w) * float(w)
    x_norm_sq = float(len(set(int(t) for t in product_tag_ids)))

    if w_norm_sq <= 0 or x_norm_sq <= 0:
        return 0.0

    return dot / (sqrt(w_norm_sq) * sqrt(x_norm_sq))

