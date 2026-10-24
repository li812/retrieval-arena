from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import session_scope
from app.core.errors import DuplicateNameError


class Repository:
    """Base for the M1 repositories. No workspace scope yet: that arrives with M2."""

    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with session_scope(self._sessions) as session:
            yield session

    def _unique(self, fn: Callable[[Session], object]):
        """Run fn in a transaction, turning a UNIQUE violation into DuplicateNameError."""
        try:
            with self._session() as session:
                return fn(session)
        except IntegrityError as exc:
            message = str(exc.orig)
            if "UNIQUE constraint failed" in message:
                raise DuplicateNameError(message) from exc
            raise
