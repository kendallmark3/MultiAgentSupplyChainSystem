"""
Embedding Matcher — Vertex AI Semantic Part Name Matching
Replaces difflib fuzzy match with proper semantic similarity.
Uses the same text-embedding-005 model as the supplier agent.
"""

import os
import math
import sys
from pathlib import Path


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(text: str) -> list:
    from google import genai
    from google.genai.types import EmbedContentConfig
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    client = genai.Client(vertexai=True, project=project, location="us-central1")
    response = client.models.embed_content(
        model="text-embedding-005",
        contents=[text],
        config=EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768
        )
    )
    return response.embeddings[0].values


# Cache embeddings so we don't call Vertex AI on every request
_cache: dict = {}


def find_best_match(query: str, part_names: list) -> tuple:
    """
    Find semantically closest part name to query.
    Returns (best_match, similarity_score).
    Falls back to difflib if Vertex AI unavailable.
    """
    if query in part_names:
        return query, 1.0

    try:
        # Embed query
        query_vec = get_embedding(query)

        # Embed all part names (cached)
        best_name = part_names[0]
        best_score = -1.0

        for name in part_names:
            if name not in _cache:
                _cache[name] = get_embedding(name)
            score = cosine_similarity(query_vec, _cache[name])
            if score > best_score:
                best_score = score
                best_name = name

        print(f"Semantic match: '{query}' -> '{best_name}' ({best_score:.3f})")
        return best_name, best_score

    except Exception as e:
        print(f"Vertex AI embedding failed: {e} - falling back to difflib")
        import difflib
        matches = difflib.get_close_matches(query, part_names, n=1, cutoff=0.3)
        if matches:
            return matches[0], 0.5
        best = max(part_names, key=lambda k: difflib.SequenceMatcher(
            None, query.lower(), k.lower()).ratio())
        return best, 0.0