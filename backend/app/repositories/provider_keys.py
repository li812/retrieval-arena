from sqlalchemy import delete, func, select, update

from app.models import ProviderKey
from app.repositories.base import Repository

_PUBLIC = (
    ProviderKey.id,
    ProviderKey.label,
    ProviderKey.provider,
    ProviderKey.api_key,
    ProviderKey.is_active,
    ProviderKey.created_at,
    ProviderKey.last_used,
)


def _public(row) -> dict:
    """Row without the secret: callers outside the server only ever see the last 4 chars."""
    d = dict(row._mapping)
    d["key_hint"] = d.pop("api_key")[-4:]
    return d


class ProviderKeyRepository(Repository):
    """Saved model-provider keys (legacy `api_keys`, plaintext until M2 encrypts them)."""

    def list_keys(self) -> list[dict]:
        with self._session() as s:
            return [_public(r) for r in s.execute(select(*_PUBLIC).order_by(ProviderKey.id))]

    def get_active_key(self, provider: str) -> dict | None:
        """The key last selected in the UI for this provider — used by server-side callers like MCP tools."""
        stmt = (
            select(ProviderKey.id, ProviderKey.label, ProviderKey.provider, ProviderKey.api_key)
            .where(ProviderKey.provider == provider)
            .order_by(ProviderKey.is_active.desc(), ProviderKey.last_used.desc(), ProviderKey.id.desc())
            .limit(1)
        )
        with self._session() as s:
            row = s.execute(stmt).first()
        return dict(row._mapping) if row else None

    def get_key(self, key_id: int) -> dict | None:
        """Full row including the plaintext key — for server-side use only."""
        stmt = select(ProviderKey.id, ProviderKey.label, ProviderKey.provider, ProviderKey.api_key).where(
            ProviderKey.id == key_id
        )
        with self._session() as s:
            row = s.execute(stmt).first()
        return dict(row._mapping) if row else None

    def save_key(self, label: str, provider: str, api_key: str) -> dict:
        def insert(s):
            key = ProviderKey(label=label, provider=provider, api_key=api_key)
            s.add(key)
            s.flush()
            return key.id

        key_id = self._unique(insert)
        with self._session() as s:
            return _public(s.execute(select(*_PUBLIC).where(ProviderKey.id == key_id)).one())

    def delete_key(self, key_id: int) -> bool:
        with self._session() as s:
            return s.execute(delete(ProviderKey).where(ProviderKey.id == key_id)).rowcount > 0

    def set_active(self, key_id: int, provider: str) -> None:
        with self._session() as s:
            s.execute(update(ProviderKey).where(ProviderKey.provider == provider).values(is_active=0))
            s.execute(
                update(ProviderKey).where(ProviderKey.id == key_id).values(is_active=1, last_used=func.datetime("now"))
            )
