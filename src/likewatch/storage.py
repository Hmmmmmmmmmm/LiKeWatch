"""SQLite event history and durable outbox. Each operation owns its connection."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .domain import uid


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY, profile TEXT, rule_id TEXT, name TEXT,
                    activated REAL, recovered REAL, acknowledged INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, profile TEXT, incident TEXT, kind TEXT,
                    created REAL, body TEXT);
                CREATE TABLE IF NOT EXISTS outbox (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE,
                    profile TEXT, incident TEXT, kind TEXT, chat TEXT, topic TEXT,
                    body TEXT, state TEXT, attempts INTEGER DEFAULT 0,
                    due REAL, created REAL, detail TEXT DEFAULT '');
            ''')
            # A process exit after send but before commit cannot prove remote delivery.
            db.execute("UPDATE outbox SET state='uncertain', detail='Interrupted during send; inspect Telegram before retrying' WHERE state='sending'")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def active(self, profile):
        with self.connection() as db:
            return {r['rule_id']: r['id'] for r in db.execute(
                'SELECT * FROM incidents WHERE profile=? AND recovered IS NULL', (profile,))}

    def enqueue(self, profile, kind, body, incident=None, rule=None, event_id=None, now=None):
        now = time.time() if now is None else now
        event_id = event_id or uid()
        body = f"[{kind}] {body}\nObserved: {time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(now))}\nEvent: {event_id}"
        with self.connection() as db:
            if db.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
                return event_id
            if kind == 'ALERT' and rule:
                db.execute('INSERT INTO incidents(id,profile,rule_id,name,activated) VALUES(?,?,?,?,?)',
                           (incident, profile.id, rule.id, rule.name, now))
            if kind == 'RECOVERY':
                db.execute('UPDATE incidents SET recovered=? WHERE id=?', (now, incident))
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)', (event_id, profile.id, incident, kind, now, body))
            if profile.delivery_enabled and profile.chat_id and kind in profile.routes:
                if kind == 'DATA':
                    db.execute("UPDATE outbox SET state='expired',detail='Superseded by newer data' WHERE profile=? AND kind='DATA' AND state IN ('queued','retrying')", (profile.id,))
                # Bound messages conservatively in UTF-16 units, avoiding Telegram's limit.
                encoded = body.encode('utf-16-le')
                if len(encoded) > 7600:
                    body = encoded[:7400].decode('utf-16-le', errors='ignore') + '\n[Truncated; complete event stored locally]'
                db.execute('INSERT INTO outbox(event_id,profile,incident,kind,chat,topic,body,state,due,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (event_id, profile.id, incident, kind, profile.chat_id, profile.topic_id, body, 'queued', now, now))
        return event_id

    def claim(self, profile, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE outbox SET state='expired',detail='Data older than 5 minutes' WHERE kind='DATA' AND state IN ('queued','retrying') AND created<?", (now-300,))
            row = db.execute('''SELECT * FROM outbox AS o WHERE profile=?
                AND state IN ('queued','retrying') AND due<=?
                AND (incident IS NULL OR NOT EXISTS (
                    SELECT 1 FROM outbox AS previous WHERE previous.incident=o.incident
                    AND previous.seq<o.seq AND previous.state IN ('queued','retrying','sending','uncertain')))
                ORDER BY CASE kind WHEN 'DATA' THEN 1 ELSE 0 END, seq LIMIT 1''', (profile, now)).fetchone()
            if row:
                db.execute("UPDATE outbox SET state='sending',attempts=attempts+1 WHERE seq=?", (row['seq'],))
                return dict(row)
        return None

    def delivered(self, seq, state, delay=0, detail=''):
        with self.connection() as db:
            db.execute('UPDATE outbox SET state=?,due=?,detail=? WHERE seq=?', (state, time.time()+delay, detail, seq))

    def acknowledge(self, incident):
        with self.connection() as db:
            db.execute('UPDATE incidents SET acknowledged=1 WHERE id=?', (incident,))

    def retry_uncertain(self, profile):
        with self.connection() as db:
            db.execute("UPDATE outbox SET state='queued',due=?,detail='Manual retry; duplicate delivery possible' WHERE profile=? AND state IN ('uncertain','failed')", (time.time(), profile))

    def history(self, profile):
        with self.connection() as db:
            return [dict(r) for r in db.execute('''SELECT e.*, COALESCE(o.state,'local') AS delivery,
                COALESCE(o.detail,'') AS detail, COALESCE(i.acknowledged,0) AS acknowledged
                FROM events e LEFT JOIN outbox o ON e.id=o.event_id
                LEFT JOIN incidents i ON e.incident=i.id
                WHERE e.profile=? ORDER BY e.created DESC LIMIT 100''', (profile,))]

    def prune(self, days=30):
        with self.connection() as db:
            cutoff = time.time()-days*86400
            db.execute("DELETE FROM outbox WHERE created<? AND state IN ('accepted','expired')", (cutoff,))
            db.execute('''DELETE FROM events WHERE created<? AND id NOT IN (SELECT event_id FROM outbox)
                AND (incident IS NULL OR incident NOT IN (SELECT id FROM incidents WHERE recovered IS NULL))''', (cutoff,))
