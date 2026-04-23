import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "/data/lab.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    mode        TEXT NOT NULL,
    scenario    TEXT,
    agent_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    tool        TEXT NOT NULL,
    params      TEXT,
    decision    TEXT NOT NULL,
    reason      TEXT,
    trace       TEXT
);
"""


async def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_CREATE_TABLE)
        await db.commit()


async def insert_event(event: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["id"], event["ts"], event["mode"], event.get("scenario"),
                event["agent_id"], event["session_id"], event["tool"],
                event.get("params"), event["decision"], event.get("reason"),
                event.get("trace"),
            ),
        )
        await db.commit()


async def get_all_events() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events ORDER BY ts") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def clear_events():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events")
        await db.commit()
