def normalize_search_query(query: str) -> str:
    return " ".join(query.strip().lower().split())
