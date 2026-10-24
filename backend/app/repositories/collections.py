from sqlalchemy import delete, select

from app.models import CollectionRecord
from app.repositories.base import Repository


class CollectionRepository(Repository):
    """Which embedding model and dimension each collection was built with."""

    def get_collection_dim(self, name: str) -> dict | None:
        stmt = select(
            CollectionRecord.name,
            CollectionRecord.embed_provider,
            CollectionRecord.embed_model,
            CollectionRecord.embed_dim,
        ).where(CollectionRecord.name == name)
        with self._session() as s:
            row = s.execute(stmt).first()
        return dict(row._mapping) if row else None

    def register_collection(self, name: str, embed_provider: str, embed_model: str, embed_dim: int) -> None:
        with self._session() as s:
            existing = s.get(CollectionRecord, name)
            if existing:
                if existing.embed_dim != embed_dim:
                    raise ValueError(
                        f"Dimension mismatch: collection '{name}' uses {existing.embed_dim}-dim "
                        f"({existing.embed_model}), but {embed_model} produces {embed_dim}-dim."
                    )
                # Same size is not enough: vectors from different models live in different spaces
                if existing.embed_model != embed_model:
                    raise ValueError(
                        f"Model mismatch: collection '{name}' was embedded with {existing.embed_model}; "
                        f"ingesting with {embed_model} would silently corrupt retrieval."
                    )
                return
            s.add(
                CollectionRecord(name=name, embed_provider=embed_provider, embed_model=embed_model, embed_dim=embed_dim)
            )

    def delete_collection(self, name: str) -> None:
        with self._session() as s:
            s.execute(delete(CollectionRecord).where(CollectionRecord.name == name))
