from sqlalchemy import delete, select, update

from app.models import HistoryEntry
from app.repositories.base import Repository

_MAX_UNPINNED = 500


class HistoryRepository(Repository):
    """Retrieval Lab query history."""

    def add_history(self, question: str, backend: str, collection: str, payload: str) -> int:
        with self._session() as s:
            entry = HistoryEntry(question=question, backend=backend, collection=collection, payload=payload)
            s.add(entry)
            s.flush()
            # Keep the table bounded; pinned entries are never trimmed
            newest = select(HistoryEntry.id).order_by(HistoryEntry.id.desc()).limit(_MAX_UNPINNED)
            s.execute(delete(HistoryEntry).where(HistoryEntry.pinned == 0, HistoryEntry.id.not_in(newest)))
            return entry.id

    def list_history(self, search: str = "", limit: int = 100) -> list[dict]:
        stmt = (
            select(
                HistoryEntry.id,
                HistoryEntry.created_at,
                HistoryEntry.question,
                HistoryEntry.backend,
                HistoryEntry.collection,
                HistoryEntry.payload,
                HistoryEntry.pinned,
            )
            .where(HistoryEntry.question.like(f"%{search}%"))
            .order_by(HistoryEntry.pinned.desc(), HistoryEntry.id.desc())
            .limit(limit)
        )
        with self._session() as s:
            return [dict(r._mapping) for r in s.execute(stmt)]

    def set_history_pinned(self, history_id: int, pinned: bool) -> bool:
        with self._session() as s:
            stmt = update(HistoryEntry).where(HistoryEntry.id == history_id).values(pinned=int(pinned))
            return s.execute(stmt).rowcount > 0

    def delete_history(self, history_id: int) -> bool:
        with self._session() as s:
            return s.execute(delete(HistoryEntry).where(HistoryEntry.id == history_id)).rowcount > 0
