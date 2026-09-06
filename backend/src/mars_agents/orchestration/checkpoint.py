import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def open_checkpointer(path: Path) -> tuple[sqlite3.Connection, SqliteSaver]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    saver = SqliteSaver(connection)
    saver.setup()
    return connection, saver
