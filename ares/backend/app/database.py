"""SQLite persistence (async SQLAlchemy).

SQLite for development; swapping ARES_SYSTEM__DATABASE_URL to a PostgreSQL
URL later requires no application changes because everything goes through
SQLAlchemy's async engine.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import JSON, Float, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .logging_setup import get_logger
from .status import ComponentState, status_registry

log = get_logger("database")


class Base(DeclarativeBase):
    pass


class JournalEntry(Base):
    __tablename__ = "journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(48), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    volume: Mapped[float] = mapped_column(Float)
    entry: Mapped[float] = mapped_column(Float)
    exit: Mapped[float] = mapped_column(Float)
    sl: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp: Mapped[float | None] = mapped_column(Float, nullable=True)
    pl: Mapped[float] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(8))          # win / loss / flat
    strategy: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    close_reason: Mapped[str] = mapped_column(String(64))
    market_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    opened_at: Mapped[str] = mapped_column(String(32))
    closed_at: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def as_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    async def start(self) -> bool:
        try:
            if self.url.startswith("sqlite"):
                db_path = self.url.split("///")[-1]
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_async_engine(self.url, echo=False)
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
            status_registry.set("database", ComponentState.ONLINE, "SQLite ready", {"url_scheme": self.url.split(":")[0]})
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("database start failed: %s", exc)
            status_registry.set("database", ComponentState.OFFLINE, f"Local storage error: {exc}")
            return False

    async def stop(self) -> None:
        if self.engine:
            await self.engine.dispose()

    async def add_journal_entry(self, trade, market_conditions: dict | None = None,
                                timeframe: str | None = None, notes: str | None = None) -> None:
        if not self.session_factory:
            log.warning("journal write skipped: database offline")
            return
        result = "win" if trade.pl > 0 else "loss" if trade.pl < 0 else "flat"
        entry = JournalEntry(
            trade_id=trade.id, symbol=trade.symbol, direction=trade.direction,
            volume=trade.volume, entry=trade.entry, exit=trade.exit,
            sl=trade.sl, tp=trade.tp, pl=trade.pl, result=result,
            strategy=trade.strategy, confidence=trade.confidence,
            close_reason=trade.close_reason, market_conditions=market_conditions,
            opened_at=trade.opened_at, closed_at=trade.closed_at,
            timeframe=timeframe, notes=notes,
        )
        async with self.session_factory() as session:
            session.add(entry)
            await session.commit()

    async def update_journal_notes(self, entry_id: int, notes: str) -> dict | None:
        if not self.session_factory:
            return None
        async with self.session_factory() as session:
            entry = await session.get(JournalEntry, entry_id)
            if entry is None:
                return None
            entry.notes = notes
            await session.commit()
            return entry.as_dict()

    async def journal_entries(self, limit: int = 200, symbol: str | None = None) -> list[dict]:
        if not self.session_factory:
            return []
        async with self.session_factory() as session:
            stmt = select(JournalEntry).order_by(JournalEntry.id.desc()).limit(limit)
            if symbol:
                stmt = stmt.where(JournalEntry.symbol == symbol)
            rows = (await session.execute(stmt)).scalars().all()
            return [r.as_dict() for r in rows]
