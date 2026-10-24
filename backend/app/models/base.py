from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class LegacyBase(DeclarativeBase):
    """For the pre-M1 tables only. Their UNIQUE and FOREIGN KEY constraints are unnamed in existing databases, so
    this metadata has no naming convention; otherwise `alembic check` would see every one of them as drift."""

    metadata = MetaData()


ALL_METADATA = [Base.metadata, LegacyBase.metadata]
