import json

from sqlalchemy import delete, func, select, update

from app.models import Conversation, Message
from app.repositories.base import Repository


class ConversationRepository(Repository):
    """Conversations and their messages, including feedback and regenerate support."""

    def list_conversations(self, bot_id: int) -> list[dict]:
        count = (
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == Conversation.id)
            .scalar_subquery()
            .label("message_count")
        )
        stmt = (
            select(
                Conversation.id,
                Conversation.bot_id,
                Conversation.title,
                Conversation.created_at,
                Conversation.updated_at,
                count,
            )
            .where(Conversation.bot_id == bot_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        )
        with self._session() as s:
            return [dict(r._mapping) for r in s.execute(stmt)]

    def create_conversation(self, bot_id: int, title: str) -> int:
        with self._session() as s:
            conv = Conversation(bot_id=bot_id, title=title[:80] or "New chat")
            s.add(conv)
            s.flush()
            return conv.id

    def get_conversation(self, conversation_id: int) -> dict | None:
        stmt = select(
            Conversation.id, Conversation.bot_id, Conversation.title, Conversation.created_at, Conversation.updated_at
        ).where(Conversation.id == conversation_id)
        with self._session() as s:
            row = s.execute(stmt).first()
        return dict(row._mapping) if row else None

    def delete_conversation(self, conversation_id: int) -> bool:
        with self._session() as s:
            return s.execute(delete(Conversation).where(Conversation.id == conversation_id)).rowcount > 0

    # --- messages ---

    def list_messages(self, conversation_id: int) -> list[dict]:
        stmt = (
            select(Message.id, Message.role, Message.content, Message.meta, Message.feedback, Message.created_at)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        )
        with self._session() as s:
            return [{**r._mapping, "meta": json.loads(r.meta)} for r in s.execute(stmt)]

    def add_message(self, conversation_id: int, role: str, content: str, meta: dict | None = None) -> int:
        with self._session() as s:
            msg = Message(conversation_id=conversation_id, role=role, content=content, meta=json.dumps(meta or {}))
            s.add(msg)
            s.flush()
            s.execute(
                update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.datetime("now"))
            )
            return msg.id

    def delete_last_assistant(self, conversation_id: int) -> None:
        """Drop the latest assistant reply (for regenerate)."""
        latest = (
            select(func.max(Message.id))
            .where(Message.conversation_id == conversation_id, Message.role == "assistant")
            .scalar_subquery()
        )
        with self._session() as s:
            s.execute(delete(Message).where(Message.id == latest))

    def set_feedback(self, message_id: int, value: int) -> bool:
        with self._session() as s:
            return s.execute(update(Message).where(Message.id == message_id).values(feedback=value)).rowcount > 0
