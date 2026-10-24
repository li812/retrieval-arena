import json

from sqlalchemy import delete, func, select, update

from app.models import Bot
from app.repositories.base import Repository

_COLUMNS = (
    Bot.id,
    Bot.name,
    Bot.emoji,
    Bot.description,
    Bot.system_prompt,
    Bot.collection,
    Bot.backend,
    Bot.provider,
    Bot.gen_model,
    Bot.embedding_model,
    Bot.key_id,
    Bot.tuning,
    Bot.greeting,
    Bot.starters,
    Bot.tools,
    Bot.created_at,
    Bot.updated_at,
)
_JSON_FIELDS = ("tuning", "starters", "tools")


def _bot(row) -> dict:
    d = dict(row._mapping)
    for f in _JSON_FIELDS:
        d[f] = json.loads(d[f])
    return d


class BotRepository(Repository):
    """Bot profiles (legacy shape: one row holds the whole configuration)."""

    def list_bots(self) -> list[dict]:
        with self._session() as s:
            return [_bot(r) for r in s.execute(select(*_COLUMNS).order_by(Bot.name))]

    def get_bot(self, bot_id: int) -> dict | None:
        with self._session() as s:
            row = s.execute(select(*_COLUMNS).where(Bot.id == bot_id)).first()
        return _bot(row) if row else None

    def save_bot(self, bot: dict, bot_id: int | None = None) -> dict:
        fields = {k: (json.dumps(v) if k in _JSON_FIELDS else v) for k, v in bot.items()}

        def write(s):
            if bot_id is None:
                row = Bot(**fields)
                s.add(row)
                s.flush()
                return row.id
            s.execute(update(Bot).where(Bot.id == bot_id).values(**fields, updated_at=func.datetime("now")))
            return bot_id

        return self.get_bot(self._unique(write))

    def delete_bot(self, bot_id: int) -> bool:
        with self._session() as s:
            return s.execute(delete(Bot).where(Bot.id == bot_id)).rowcount > 0
