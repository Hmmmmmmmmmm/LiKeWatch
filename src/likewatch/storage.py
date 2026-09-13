"""SQLite event history and durable outbox. Each operation owns its connection."""

import html
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
            db.executescript("""
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
            """)
            incident_columns = {r[1] for r in db.execute("PRAGMA table_info(incidents)")}
            if "alarm_required" not in incident_columns:
                db.execute("ALTER TABLE incidents ADD COLUMN alarm_required INTEGER DEFAULT 0")
            columns = {r[1] for r in db.execute("PRAGMA table_info(outbox)")}
            for name, kind in (("attachment", "BLOB"), ("message_id", "INTEGER"), ("rich", "INTEGER DEFAULT 0")):
                if name not in columns:
                    db.execute(f"ALTER TABLE outbox ADD COLUMN {name} {kind}")
            db.execute("CREATE TABLE IF NOT EXISTS telegram_cursor (profile TEXT PRIMARY KEY, offset INTEGER)")
            # A process exit after send but before commit cannot prove remote delivery.
            db.execute(
                "UPDATE outbox SET state='uncertain', detail='Interrupted during send; inspect Telegram before retrying' WHERE state='sending'"
            )

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
            return {
                r["rule_id"]: r["id"]
                for r in db.execute(
                    "SELECT * FROM incidents WHERE profile=? AND recovered IS NULL",
                    (profile,),
                )
            }

    def enqueue(
        self, profile, kind, body, incident=None, rule=None, event_id=None, now=None, attachment=None
    ):
        now = time.time() if now is None else now
        event_id = event_id or uid()
        # Bound plain content before escaping, preserving valid HTML and captions.
        limit = 300 if attachment else 1500
        body = body[:limit] + ("…" if len(body) > limit else "")
        body = (f"<b>{html.escape(kind)}</b>\n\n{html.escape(body)}"
                f"\nSource: {html.escape(profile.source)}"
                f"\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(now))}"
                f"\nEvent ID: <code>{html.escape(event_id)}</code>")
        if incident and kind in ("ALERT", "TEST"):
            body += "\nReply to this message with ACK to acknowledge."
        with self.connection() as db:
            if db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone():
                return event_id
            if kind == "ALERT" and rule:
                db.execute(
                    "INSERT INTO incidents(id,profile,rule_id,name,activated,alarm_required) VALUES(?,?,?,?,?,?)",
                    (incident, profile.id, rule.id, rule.name, now, int(profile.local_alarm)),
                )
            if kind == "TEST" and incident:
                # Recover immediately so a synthetic incident never enters rule state.
                db.execute(
                    "INSERT INTO incidents(id,profile,rule_id,name,activated,recovered,alarm_required) VALUES(?,?,?,?,?,?,?)",
                    (incident, profile.id, None, "Test incident", now, now, int(profile.local_alarm)),
                )
            if kind == "RECOVERY":
                db.execute(
                    "UPDATE incidents SET recovered=? WHERE id=?", (now, incident)
                )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (event_id, profile.id, incident, kind, now, body),
            )
            if profile.delivery_enabled and profile.chat_id and (kind in profile.routes or kind == "TEST"):
                if kind == "DATA":
                    db.execute(
                        "UPDATE outbox SET state='expired',detail='Superseded by newer data' WHERE profile=? AND kind='DATA' AND state IN ('queued','retrying')",
                        (profile.id,),
                    )
                db.execute(
                    "INSERT INTO outbox(event_id,profile,incident,kind,chat,topic,body,state,due,created,attachment,rich) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                    (
                        event_id,
                        profile.id,
                        incident,
                        kind,
                        profile.chat_id,
                        profile.topic_id,
                        body,
                        "queued",
                        now,
                        now,
                        attachment,
                    ),
                )
        return event_id

    def claim(self, profile, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE outbox SET state='expired',detail='Data older than 5 minutes' WHERE kind='DATA' AND state IN ('queued','retrying') AND created<?",
                (now - 300,),
            )
            row = db.execute(
                """SELECT * FROM outbox AS o WHERE profile=?
                AND state IN ('queued','retrying') AND due<=?
                AND (incident IS NULL OR NOT EXISTS (
                    SELECT 1 FROM outbox AS previous WHERE previous.incident=o.incident
                    AND previous.seq<o.seq AND previous.state IN ('queued','retrying','sending','uncertain')))
                ORDER BY CASE kind WHEN 'DATA' THEN 1 ELSE 0 END, seq LIMIT 1""",
                (profile, now),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE outbox SET state='sending',attempts=attempts+1 WHERE seq=?",
                    (row["seq"],),
                )
                return dict(row)
        return None

    def delivered(self, seq, state, delay=0, detail="", message_id=None):
        with self.connection() as db:
            db.execute(
                "UPDATE outbox SET state=?,due=?,detail=?,message_id=COALESCE(?,message_id) WHERE seq=?",
                (state, time.time() + delay, detail, message_id, seq),
            )

    def acknowledge(self, incident):
        with self.connection() as db:
            db.execute("UPDATE incidents SET acknowledged=1 WHERE id=?", (incident,))

    def retry_uncertain(self, profile):
        with self.connection() as db:
            db.execute(
                "UPDATE outbox SET state='queued',due=?,detail='Manual retry; duplicate delivery possible' WHERE profile=? AND state IN ('uncertain','failed')",
                (time.time(), profile),
            )

    def history(self, profile):
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute(
                    """SELECT e.*, COALESCE(o.state,'local') AS delivery,
                COALESCE(o.detail,'') AS detail, COALESCE(i.acknowledged,0) AS acknowledged
                FROM events e LEFT JOIN outbox o ON e.id=o.event_id
                LEFT JOIN incidents i ON e.incident=i.id
                WHERE e.profile=? ORDER BY e.created DESC LIMIT 100""",
                    (profile,),
                )
            ]

    def prune(self, days=30):
        with self.connection() as db:
            cutoff = time.time() - days * 86400
            db.execute(
                "DELETE FROM outbox WHERE created<? AND state IN ('accepted','expired')",
                (cutoff,),
            )
            db.execute(
                """DELETE FROM events WHERE created<? AND id NOT IN (SELECT event_id FROM outbox)
                AND (incident IS NULL OR incident NOT IN (SELECT id FROM incidents WHERE recovered IS NULL))""",
                (cutoff,),
            )

    def pending_alarms(self, profile):
        with self.connection() as db:
            return [r[0] for r in db.execute("SELECT id FROM incidents WHERE profile=? AND acknowledged=0 AND alarm_required=1", (profile,))]

    def ack_reply(self, profile, chat, topic, message_id):
        with self.connection() as db:
            row = db.execute("SELECT incident FROM outbox WHERE profile=? AND chat=? AND (COALESCE(topic,'')='' OR topic=?) AND message_id=? AND state='accepted' AND incident IS NOT NULL", (profile, str(chat), str(topic or ''), message_id)).fetchone()
            if row:
                db.execute("UPDATE incidents SET acknowledged=1 WHERE id=?", (row[0],))
                return True
        return False

    def ack_single_pending(self, profile, chat, topic, sent_at):
        """A bare ACK is safe only for one pending incident in this destination."""
        with self.connection() as db:
            rows = db.execute(
                """SELECT DISTINCT i.id FROM incidents i JOIN outbox o ON o.incident=i.id
                WHERE o.profile=? AND o.chat=? AND COALESCE(o.topic,'')=?
                AND o.state='accepted' AND o.message_id IS NOT NULL
                AND i.acknowledged=0 AND CAST(i.activated AS INTEGER)<=?""",
                (profile, str(chat), str(topic or ''), sent_at),
            ).fetchall()
            if len(rows) == 1:
                db.execute("UPDATE incidents SET acknowledged=1 WHERE id=?", (rows[0][0],))
                return True
        return False

    def update_offset(self, profile, offset=None):
        with self.connection() as db:
            if offset is not None:
                db.execute("INSERT INTO telegram_cursor VALUES(?,?) ON CONFLICT(profile) DO UPDATE SET offset=excluded.offset", (profile,offset))
            row=db.execute("SELECT offset FROM telegram_cursor WHERE profile=?",(profile,)).fetchone()
            return row[0] if row else 0

    def has_ack_targets(self, profile):
        with self.connection() as db:
            return db.execute("SELECT 1 FROM outbox o JOIN incidents i ON o.incident=i.id WHERE o.profile=? AND o.state='accepted' AND o.message_id IS NOT NULL AND i.acknowledged=0 LIMIT 1", (profile,)).fetchone() is not None
