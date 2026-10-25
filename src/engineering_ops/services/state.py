"""Local SQLite transactions shared across workers. No Jira credentials are stored."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock


class StateDatabase:
    def __init__(self, path=None):
        self.path = str(path) if path is not None else ":memory:"
        if self.path != ":memory:":
            target = Path(self.path).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            # Create without a window in which approval data is world-readable.
            import os
            fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            target.chmod(0o600)
            self.path = str(target)
        self.lock = RLock()
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS executions (
                preview_id TEXT PRIMARY KEY, action TEXT NOT NULL, instance TEXT NOT NULL,
                actor TEXT NOT NULL, operation_key TEXT NOT NULL, source_version TEXT NOT NULL,
                status TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL,
                owner_pid INTEGER
            );
            CREATE TABLE IF NOT EXISTS claims (
                resource TEXT PRIMARY KEY, preview_id TEXT NOT NULL REFERENCES executions(preview_id)
            );
            CREATE TABLE IF NOT EXISTS steps (
                preview_id TEXT NOT NULL REFERENCES executions(preview_id), step_id TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL,
                result TEXT, error TEXT, PRIMARY KEY (preview_id, step_id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL
            );
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise

    def close(self):
        self.connection.close()
