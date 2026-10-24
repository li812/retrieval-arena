from fastapi import HTTPException, Request

from app.core.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def resolve_key(svc: Services, api_key: str | None, key_id: int | None) -> str:
    """Prefer a saved key looked up server-side, so the secret never has to leave the server."""
    if key_id is not None:
        row = svc.provider_keys.get_key(key_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Saved key {key_id} not found")
        return row["api_key"]
    if api_key:
        return api_key
    raise HTTPException(status_code=400, detail="Provide api_key or key_id")


def embedding_mismatch(collections, collection: str, embedding_model: str, embedding: list[float]) -> str | None:
    """Guard: the query must be embedded by the same model (and so the same space) as the collection."""
    col_info = collections.get_collection_dim(collection)
    if not col_info:
        return None
    if col_info["embed_dim"] != len(embedding):
        return (
            f"Dimension mismatch: collection '{collection}' uses {col_info['embed_dim']}-dim "
            f"({col_info['embed_model']}), but {embedding_model} produces {len(embedding)}-dim."
        )
    if col_info["embed_model"] != embedding_model:
        return (
            f"Model mismatch: collection '{collection}' was embedded with {col_info['embed_model']}; "
            f"select that embedding model to query it."
        )
    return None
