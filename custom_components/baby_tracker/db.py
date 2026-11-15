"""SQLite storage and bottle rules. Everything is synchronous: call it in the executor.

Model:
- bottle: what was prepared (oz). It stays open until it is closed or fully consumed.
- feeding: each time the baby eats; adds oz to a bottle.
Dates are ISO 8601 UTC ("...+00:00"), comparable as text.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

# Hours: "formula"/"breast_milk" since the first feeding; "room"/"fridge" since it was made
Limits = dict

SCHEMA_VERSION = 1
EPS = 1e-6

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    ended_at TEXT NOT NULL,
    oz_prepared REAL,
    oz_leftover REAL,
    oz_taken REAL NOT NULL,
    type TEXT NOT NULL DEFAULT 'formula',
    confidence TEXT NOT NULL DEFAULT 'exact',
    source TEXT,
    logged_by TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    modified_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    bottle_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_feedings_ended_at ON feedings(ended_at);
CREATE INDEX IF NOT EXISTS idx_feedings_bottle ON feedings(bottle_id);
CREATE TABLE IF NOT EXISTS bottles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prepared_at TEXT NOT NULL,
    oz REAL NOT NULL,
    type TEXT NOT NULL DEFAULT 'formula',
    closed_at TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    made_at TEXT,
    location TEXT,
    in_stash INTEGER NOT NULL DEFAULT 0,
    pumping_id INTEGER,
    activated_at TEXT
);
CREATE TABLE IF NOT EXISTS pumpings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ended_at TEXT NOT NULL,
    oz_left REAL,
    oz_right REAL,
    duration_min REAL,
    note TEXT,
    logged_by TEXT,
    created_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pumpings_ended_at ON pumpings(ended_at);
CREATE TABLE IF NOT EXISTS diapers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ended_at TEXT NOT NULL,
    type TEXT NOT NULL,
    color TEXT,
    consistency TEXT,
    note TEXT,
    source TEXT,
    logged_by TEXT,
    created_at TEXT NOT NULL,
    modified_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_diapers_ended_at ON diapers(ended_at);
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    weight_kg REAL,
    height_cm REAL,
    head_cm REAL,
    note TEXT,
    logged_by TEXT,
    created_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_measurements_date ON measurements(date);
CREATE TABLE IF NOT EXISTS milestones (
    milestone_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    note TEXT,
    logged_by TEXT,
    created_at TEXT NOT NULL,
    modified_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
"""

FEEDING_FIELDS = (
    "started_at", "ended_at", "oz_taken", "type", "confidence", "source",
    "logged_by", "note", "bottle_id",
)

BOTTLE_SQL = """
SELECT b.*, COALESCE(SUM(t.oz_taken), 0) AS consumed, COUNT(t.id) AS n_feedings,
       MIN(t.ended_at) AS first_feeding, MAX(t.ended_at) AS last_feeding
FROM bottles b
LEFT JOIN feedings t ON t.bottle_id = b.id AND t.deleted = 0
WHERE b.deleted = 0 {filter}
GROUP BY b.id
"""


class BabyError(ValueError):
    """Validation error shown to the user; `key` is in the "exceptions" section of the translations."""

    def __init__(self, key: str, **data: Any) -> None:
        super().__init__(key)
        self.key = key
        self.data = {k: str(v) for k, v in data.items()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stamp_iso() -> str:
    """Like now_iso but with microseconds: orders actions made within the same second."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _r(v: float) -> float:
    return round(v + 0.0, 2)


def bottle_state(b: dict[str, Any]) -> str:
    if b["consumed"] >= b["oz"] - EPS:
        return "finished"
    return "incomplete" if b["closed_at"] else "open"


def _limits(lim: Limits | float | None) -> Limits | None:
    if lim is None or isinstance(lim, dict):
        return lim
    return {"formula": lim, "breast_milk": lim, "room": 4.0, "fridge": 96.0}


def _enrich(b: dict[str, Any], lim: Limits | float | None = None) -> dict[str, Any]:
    b = dict(b)
    lim = _limits(lim)
    now = datetime.now(timezone.utc)
    b["consumed"] = _r(b["consumed"])
    b["remaining"] = _r(max(0.0, b["oz"] - b["consumed"]))
    b["state"] = "stash" if b.get("in_stash") else bottle_state(b)
    b["wasted"] = b["remaining"] if b["state"] == "incomplete" else 0.0
    b["use_by"], b["past_use_by"], b["expires_at"], b["expired"] = None, False, None, False
    if lim is None:
        return b
    # Expiry by storage (breast milk): since it was made, depending on where it is
    if b.get("made_at") and b.get("location") in ("room", "fridge"):
        expires_at = _dt(b["made_at"]) + timedelta(hours=lim[b["location"]])
        b["expires_at"] = expires_at.isoformat(timespec="seconds")
        b["expired"] = b["state"] in ("stash", "open") and now > expires_at
    # Limit since the first feeding (formula / breast milk), capped by the storage expiry
    if b["first_feeding"]:
        limit = lim["breast_milk"] if b.get("type") == "breast_milk" else lim["formula"]
        use_by = _dt(b["first_feeding"]) + timedelta(hours=limit)
        if b["expires_at"]:
            use_by = min(use_by, _dt(b["expires_at"]))
        b["use_by"] = use_by.isoformat(timespec="seconds")
        b["past_use_by"] = b["state"] == "open" and now > use_by
    return b


class BabyDB:
    """Access to /config/baby_tracker.db."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------------ schema
    def initialize(self) -> None:
        with self._con() as con:
            con.executescript(SCHEMA_SQL)
            if con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
                con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ------------------------------------------------------------ bottles
    def _bottle(self, con: sqlite3.Connection, bid: int) -> dict[str, Any] | None:
        f = con.execute(BOTTLE_SQL.format(filter="AND b.id = ?"), (bid,)).fetchone()
        return dict(f) if f else None

    def _open_bottles(self, con: sqlite3.Connection) -> list[dict[str, Any]]:
        """Open bottles with milk: the first is the current bottle, the rest are paused."""
        rows = con.execute(
            BOTTLE_SQL.format(filter="AND b.closed_at IS NULL AND b.in_stash = 0")
            + f" HAVING consumed < b.oz - {EPS} ORDER BY COALESCE(b.activated_at, b.prepared_at) DESC, b.id DESC"
        ).fetchall()
        return [dict(f) for f in rows]

    def _open_bottle(self, con: sqlite3.Connection) -> dict[str, Any] | None:
        open_bottles = self._open_bottles(con)
        return open_bottles[0] if open_bottles else None

    def _close(self, con: sqlite3.Connection, b: dict[str, Any], when: str) -> None:
        """Closes a bottle. A formula bottle with no feedings is discarded (e.g. a "new" pressed by mistake);
        breast milk with no feedings is closed instead, because tossing it counts as wasted milk."""
        if b["n_feedings"] == 0 and b["type"] != "breast_milk":
            con.execute("UPDATE bottles SET deleted = 1 WHERE id = ?", (b["id"],))
        else:
            con.execute("UPDATE bottles SET closed_at = ? WHERE id = ?", (when, b["id"]))

    def _close_open_bottles(self, con: sqlite3.Connection, when: str) -> None:
        for b in con.execute(BOTTLE_SQL.format(filter="AND b.closed_at IS NULL AND b.in_stash = 0")).fetchall():
            self._close(con, dict(b), when)

    def _create(self, con: sqlite3.Connection, oz: float, type: str, prepared_at: str,
               closed_at: str | None = None) -> dict[str, Any]:
        if closed_at is None:
            self._close_open_bottles(con, prepared_at)
        bid = con.execute(
            "INSERT INTO bottles (prepared_at, oz, type, closed_at, created_at, activated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (prepared_at, oz, type, closed_at, now_iso(), prepared_at),
        ).lastrowid
        return self._bottle(con, bid)

    def current_bottle(self, lim: Limits | float) -> dict[str, Any] | None:
        with self._con() as con:
            b = self._open_bottle(con)
        return _enrich(b, lim) if b else None

    def paused_bottles(self, lim: Limits | float) -> list[dict[str, Any]]:
        with self._con() as con:
            return [_enrich(b, lim) for b in self._open_bottles(con)[1:]]

    def resume_bottle(self, bid: int, lim: Limits | float) -> dict[str, Any]:
        """A paused bottle becomes the current bottle again."""
        with self._con() as con:
            if not any(b["id"] == bid for b in self._open_bottles(con)):
                raise BabyError("bottle_not_open", id=bid)
            previous = self._open_bottle(con)
            con.execute("UPDATE bottles SET activated_at = ? WHERE id = ?", (stamp_iso(), bid))
            b = self._bottle(con, bid)
            previous = self._bottle(con, previous["id"]) if previous and previous["id"] != bid else None
        return {"bottle": _enrich(b, lim), "previous": _enrich(previous, lim) if previous else None}

    def get_bottle(self, bid: int, lim: Limits | float | None = None) -> dict[str, Any] | None:
        with self._con() as con:
            b = self._bottle(con, bid)
        return _enrich(b, lim) if b else None

    def new_bottle(self, oz: float, type: str, lim: Limits | float) -> dict[str, Any]:
        with self._con() as con:
            previous = self._open_bottle(con)
            new = self._create(con, oz, type, now_iso())
            previous = self._bottle(con, previous["id"]) if previous else None
        return {
            "bottle": _enrich(new, lim),
            "previous": _enrich(previous, lim) if previous else None,
        }

    def close_bottle(self, bid: int | None, lim: Limits | float) -> dict[str, Any]:
        with self._con() as con:
            b = self._bottle(con, bid) if bid else self._open_bottle(con)
            if not b:
                raise BabyError("no_open_bottle")
            self._close(con, b, now_iso())
            closed_at = self._bottle(con, b["id"])
        if closed_at is None:  # formula with no feedings: discarded without counting as waste
            return {**_enrich(b, lim), "state": "discarded", "wasted": 0.0}
        return _enrich(closed_at, lim)

    def delete_bottle(self, bid: int) -> dict[str, Any]:
        """Undoes a bottle with no feedings and reopens the one that was closed when it was created."""
        with self._con() as con:
            b = self._bottle(con, bid)
            if not b:
                raise BabyError("bottle_not_found", id=bid)
            if b["n_feedings"]:
                raise BabyError("bottle_has_feedings")
            con.execute("UPDATE bottles SET deleted = 1 WHERE id = ?", (bid,))
            prev = con.execute(
                "SELECT id FROM bottles WHERE deleted = 0 AND in_stash = 0 AND id < ? AND closed_at = ? "
                "ORDER BY id DESC LIMIT 1", (bid, b["prepared_at"]),
            ).fetchone()
            if prev:
                con.execute("UPDATE bottles SET closed_at = NULL WHERE id = ?", (prev["id"],))
        return {"id": bid, "reopened": prev["id"] if prev else None}

    def correct_bottle(self, bid: int, changes: dict[str, Any], lim: Limits | float) -> dict[str, Any]:
        """stash_id: the bottle came from that stash milk; it becomes breast milk with its data
        (when it was made, where, pumping) and the stash one is removed without counting as wasted."""
        changes = dict(changes)
        with self._con() as con:
            if changes.get("stash_id"):
                r = self._of_stash(con, changes["stash_id"])
                current = self._bottle(con, bid)
                if not current or current["in_stash"]:
                    raise BabyError("bottle_not_found", id=bid)
                changes.update(type="breast_milk", made_at=r["made_at"], location=r["location"],
                               oz=changes.get("oz") or max(r["oz"], current["consumed"]))
                con.execute("UPDATE bottles SET pumping_id = ? WHERE id = ?", (r["pumping_id"], bid))
                con.execute("UPDATE bottles SET deleted = 1 WHERE id = ?", (r["id"],))
        fields = [c for c in ("oz", "type", "note", "made_at", "location") if c in changes]
        with self._con() as con:
            if fields:
                con.execute(
                    f"UPDATE bottles SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ? AND deleted = 0",
                    [changes[c] for c in fields] + [bid],
                )
            if "type" in changes:
                # Feedings have the milk type of their bottle
                con.execute("UPDATE feedings SET type = ? WHERE bottle_id = ? AND deleted = 0", (changes["type"], bid))
            if "made_at" in changes:
                # In the stash, the preparation date is when it was made
                con.execute("UPDATE bottles SET prepared_at = made_at WHERE id = ? AND in_stash = 1", (bid,))
            if changes.get("reopen"):
                con.execute("UPDATE bottles SET closed_at = NULL WHERE id = ?", (bid,))
            b = self._bottle(con, bid)
        if not b:
            raise BabyError("bottle_not_found", id=bid)
        return _enrich(b, lim)

    def bottles_range(self, since: str, until: str, lim: Limits | float) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                BOTTLE_SQL.format(filter="AND b.prepared_at >= ? AND b.prepared_at < ?")
                + " ORDER BY b.prepared_at", (since, until),
            ).fetchall()
        return [_enrich(dict(f), lim) for f in rows]

    # ------------------------------------------------------------ breast milk
    def save_milk(self, oz: float, made_at: str, location: str, lim: Limits,
                      pumping_id: int | None = None, note: str | None = None) -> dict[str, Any]:
        """Breast-milk bottle in the stash: it is not the current bottle until it is used."""
        with self._con() as con:
            bid = self._insert_stash(con, oz, made_at, location, pumping_id, note)
            b = self._bottle(con, bid)
        return _enrich(b, lim)

    def _insert_stash(self, con, oz, made_at, location, pumping_id, note) -> int:
        return con.execute(
            "INSERT INTO bottles (prepared_at, oz, type, note, created_at, made_at, location, in_stash, pumping_id) "
            "VALUES (?, ?, 'breast_milk', ?, ?, ?, ?, 1, ?)",
            (made_at, oz, note, now_iso(), made_at, location, pumping_id),
        ).lastrowid

    def _of_stash(self, con: sqlite3.Connection, bid: int) -> dict[str, Any]:
        b = self._bottle(con, bid)
        if not b or not b["in_stash"]:
            raise BabyError("not_in_stash", id=bid)
        return b

    def stashes(self, lim: Limits) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                BOTTLE_SQL.format(filter="AND b.in_stash = 1") + " ORDER BY b.made_at"
            ).fetchall()
        return [_enrich(dict(f), lim) for f in rows]

    def use_stash(self, bid: int | None, lim: Limits, pause_current: bool = True) -> dict[str, Any]:
        """The stash bottle becomes the current bottle (no id: the oldest one that has not expired).
        pause_current=True: the bottle that was current is paused; False: it is closed (tossed)."""
        available = self.stashes(lim)
        if bid is None:
            current = [b for b in available if not b["expired"]]
            if not (current or available):
                raise BabyError("no_stash")
            bid = (current or available)[0]["id"]
        elif not any(b["id"] == bid for b in available):
            raise BabyError("not_in_stash", id=bid)
        now = now_iso()
        with self._con() as con:
            previous = self._open_bottle(con)
            if not pause_current:
                self._close_open_bottles(con, now)
            con.execute("UPDATE bottles SET in_stash = 0, prepared_at = ?, activated_at = ? WHERE id = ?",
                        (now, stamp_iso(), bid))
            b = self._bottle(con, bid)
            previous = self._bottle(con, previous["id"]) if previous else None
        return {"bottle": _enrich(b, lim), "previous": _enrich(previous, lim) if previous else None}

    def move_stash(self, bid: int, location: str, lim: Limits) -> dict[str, Any]:
        with self._con() as con:
            cur = con.execute(
                "UPDATE bottles SET location = ? WHERE id = ? AND in_stash = 1 AND deleted = 0",
                (location, bid),
            )
            if not cur.rowcount:
                raise BabyError("not_in_stash", id=bid)
            b = self._bottle(con, bid)
        return _enrich(b, lim)

    def discard_stash(self, bid: int, lim: Limits) -> dict[str, Any]:
        """Wastes a stash bottle (counts as wasted milk)."""
        with self._con() as con:
            cur = con.execute(
                "UPDATE bottles SET in_stash = 0, closed_at = ? WHERE id = ? AND in_stash = 1 AND deleted = 0",
                (now_iso(), bid),
            )
            if not cur.rowcount:
                raise BabyError("not_in_stash", id=bid)
            b = self._bottle(con, bid)
        return _enrich(b, lim)

    def log_pumping(self, *, ended_at: str, oz_left: float | None, oz_right: float | None,
                             duration_min: float | None, note: str | None, user: str | None,
                             bottles: list[float], location: str, lim: Limits) -> dict[str, Any]:
        if not (oz_left or oz_right):
            raise BabyError("missing_side")
        with self._con() as con:
            eid = con.execute(
                "INSERT INTO pumpings (ended_at, oz_left, oz_right, duration_min, note, logged_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ended_at, oz_left, oz_right, duration_min, note, user, now_iso()),
            ).lastrowid
            ids = [self._insert_stash(con, oz, ended_at, location, eid, None) for oz in bottles if oz > 0]
            bibs = [_enrich(self._bottle(con, i), lim) for i in ids]
        return {"id": eid, "ended_at": ended_at, "oz_total": _r((oz_left or 0) + (oz_right or 0)), "bottles": bibs}

    def pumpings_range(self, since: str, until: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                "SELECT e.*, COALESCE(e.oz_left, 0) + COALESCE(e.oz_right, 0) AS oz_total "
                "FROM pumpings e WHERE e.deleted = 0 AND e.ended_at >= ? AND e.ended_at < ? ORDER BY e.ended_at",
                (since, until),
            ).fetchall()
        return [dict(f) for f in rows]

    def delete_pumping(self, eid: int) -> bool:
        """Deletes the pumping session and its bottles that are still unused in the stash."""
        with self._con() as con:
            cur = con.execute("UPDATE pumpings SET deleted = 1 WHERE id = ? AND deleted = 0", (eid,))
            con.execute("UPDATE bottles SET deleted = 1 WHERE pumping_id = ? AND in_stash = 1", (eid,))
            return cur.rowcount > 0

    # ------------------------------------------------------------ feedings
    def log(
        self, *, ended_at: str, oz: float | None, type: str | None, source: str, confidence: str,
        user: str | None, note: str | None, new_bottle: bool, oz_leftover: float | None,
        accumulate_s: int, oz_default: float, lim: Limits | float, live: bool,
        bottle_type: str = "formula", stash_id: int | None = None, pause_current: bool = True,
    ) -> dict[str, Any]:
        """Logs oz taken into the appropriate bottle.

        - oz=None with oz_leftover given: the baby took what was left minus what remained (0 = "what was left").
        - It always continues the open bottle; a new one is created only if none is open,
          if requested (new_bottle) or if the amount exceeds what is left. The excess goes first to a
          paused bottle and, if there is none, to a new formula bottle.
        - accumulate_s > 0: if the bottle's last feeding has the same source and is less than
          accumulate_s seconds old, the amount is added to it (consecutive button taps = one feeding).
        - live only matters when a "new bottle" is flagged (not for feedings with a past time).
        - stash_id: the feeding is from that stash bottle, which becomes the current bottle;
          the one that was current is paused (pause_current) or closed.
        - The feeding has its bottle's milk type; `type` only decides the type of a new bottle.
        """
        with self._con() as con:
            previous = None
            created_at = False
            b = None if new_bottle or stash_id else self._open_bottle(con)
            if stash_id:
                self._of_stash(con, stash_id)
                previous = self._open_bottle(con)
                if not pause_current:
                    self._close_open_bottles(con, ended_at)
                con.execute("UPDATE bottles SET in_stash = 0, prepared_at = ?, activated_at = ? WHERE id = ?",
                            (ended_at, stamp_iso(), stash_id))
                b = self._bottle(con, stash_id)
                created_at = True
            elif b is None:
                last = con.execute(
                    "SELECT id FROM bottles WHERE deleted = 0 AND in_stash = 0 ORDER BY id DESC LIMIT 1"
                ).fetchone()
                previous = self._bottle(con, last["id"]) if last else None
                # A new bottle has the given type or, failing that, the baby's main milk type
                b = self._create(con, oz_default, type or bottle_type, ended_at)
                created_at = True

            remaining = b["oz"] - b["consumed"]
            if oz is None:
                if oz_leftover is None:
                    raise BabyError("missing_how_much")
                oz = remaining - oz_leftover
            oz = _r(oz)
            if oz <= 0:
                raise BabyError("positive_amount")

            in_b = _r(min(oz, remaining))
            excess = _r(oz - in_b)
            feeding_id = self._add_feeding(con, b["id"], in_b, ended_at, b["type"], source, confidence,
                                       user, note, accumulate_s)
            ids = [feeding_id]
            new_bottle = created_at and live
            while excess > 0:
                previous = self._bottle(con, b["id"])
                # The excess continues in a paused bottle (e.g. the formula after breast milk);
                # if there is none, in a new one of the baby's main milk type
                following = next((x for x in self._open_bottles(con) if x["id"] != b["id"]), None)
                if following:
                    b = following
                    con.execute("UPDATE bottles SET activated_at = ? WHERE id = ?", (ended_at, b["id"]))
                else:
                    b = self._create(con, max(oz_default, excess), bottle_type, ended_at)
                    new_bottle = True
                part = _r(min(excess, b["oz"] - b["consumed"]))
                feeding_id = self._add_feeding(con, b["id"], part, ended_at, b["type"], source, confidence,
                                           user, note, accumulate_s)
                ids.append(feeding_id)
                excess = _r(excess - part)
                b = self._bottle(con, b["id"])
            if previous:
                previous = self._bottle(con, previous["id"])
            feeding = dict(con.execute("SELECT * FROM feedings WHERE id = ?", (feeding_id,)).fetchone())
            b = self._bottle(con, b["id"])
        return {
            "id": feeding["id"], "ended_at": feeding["ended_at"], "oz_taken": feeding["oz_taken"],
            "confidence": feeding["confidence"], "source": feeding["source"],
            "oz_logged": oz, "feedings": ids,
            "bottle": _enrich(b, lim),
            "new_bottle": new_bottle,
            "previous": _enrich(previous, lim) if previous else None,
        }

    def _add_feeding(self, con, bid, oz, ended_at, type, source, confidence, user, note, accumulate_s) -> int:
        if accumulate_s > 0:
            last = con.execute(
                "SELECT * FROM feedings WHERE bottle_id = ? AND deleted = 0 ORDER BY ended_at DESC, id DESC LIMIT 1",
                (bid,),
            ).fetchone()
            if last and last["source"] == source and 0 <= (_dt(ended_at) - _dt(last["ended_at"])).total_seconds() <= accumulate_s:
                con.execute(
                    "UPDATE feedings SET oz_taken = ?, ended_at = ?, modified_at = ? WHERE id = ?",
                    (_r(last["oz_taken"] + oz), ended_at, now_iso(), last["id"]),
                )
                return last["id"]
        return con.execute(
            "INSERT INTO feedings (ended_at, oz_taken, type, confidence, source, logged_by, note, bottle_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ended_at, oz, type, confidence, source, user, note, bid, now_iso()),
        ).lastrowid

    def get_feeding(self, feeding_id: int) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM feedings WHERE id = ? AND deleted = 0", (feeding_id,)).fetchone()
        return dict(row) if row else None

    def update_feeding(self, feeding_id: int, changes: dict[str, Any]) -> bool:
        fields = [c for c in FEEDING_FIELDS if c in changes]
        if not fields:
            return False
        sets = ", ".join(f"{c} = ?" for c in fields)
        with self._con() as con:
            cur = con.execute(
                f"UPDATE feedings SET {sets}, modified_at = ? WHERE id = ? AND deleted = 0",
                [changes[c] for c in fields] + [now_iso(), feeding_id],
            )
            return cur.rowcount > 0

    def move_feeding(self, feeding_id: int, target: str, oz_default: float) -> int:
        """target='new': the feeding (and the later ones in its bottle) move to a new bottle.
        target='previous': the feeding merges into the previous bottle."""
        with self._con() as con:
            t = con.execute("SELECT * FROM feedings WHERE id = ? AND deleted = 0", (feeding_id,)).fetchone()
            if not t:
                raise BabyError("feeding_not_found", id=feeding_id)
            origin = self._bottle(con, t["bottle_id"]) if t["bottle_id"] else None
            if target == "new":
                open = origin is not None and origin["closed_at"] is None
                new = con.execute(
                    "INSERT INTO bottles (prepared_at, oz, type, closed_at, created_at) VALUES (?, ?, ?, ?, ?)",
                    (t["ended_at"], origin["oz"] if origin else oz_default, t["type"],
                     None if open else (origin["closed_at"] if origin else t["ended_at"]), now_iso()),
                ).lastrowid
                if origin:
                    con.execute(
                        "UPDATE feedings SET bottle_id = ? WHERE bottle_id = ? AND deleted = 0 AND (ended_at > ? OR id = ?)",
                        (new, origin["id"], t["ended_at"], feeding_id),
                    )
                    if open:
                        con.execute("UPDATE bottles SET closed_at = ? WHERE id = ?", (t["ended_at"], origin["id"]))
                else:
                    con.execute("UPDATE feedings SET bottle_id = ? WHERE id = ?", (new, feeding_id))
                target_id = new
            elif target == "previous":
                prev = con.execute(
                    "SELECT id FROM bottles WHERE deleted = 0 AND in_stash = 0 AND id < ? ORDER BY id DESC LIMIT 1",
                    (t["bottle_id"] or 10**12,),
                ).fetchone()
                if not prev:
                    raise BabyError("no_previous_bottle")
                target_id = prev["id"]
                d = self._bottle(con, target_id)
                if d["consumed"] + t["oz_taken"] > d["oz"] + EPS:
                    raise BabyError("previous_no_room", free=_r(d["oz"] - d["consumed"]))
                con.execute("UPDATE feedings SET bottle_id = ? WHERE id = ?", (target_id, feeding_id))
            else:
                raise BabyError("invalid_target")
            if origin:
                rest = self._bottle(con, origin["id"])
                if rest and rest["n_feedings"] == 0:
                    # If the source was left empty and was open, the target inherits its state
                    if rest["closed_at"] is None:
                        con.execute("UPDATE bottles SET closed_at = NULL WHERE id = ?", (target_id,))
                    con.execute("UPDATE bottles SET deleted = 1 WHERE id = ?", (origin["id"],))
        return target_id

    def delete_feeding(self, feeding_id: int) -> bool:
        """Soft delete. A closed bottle left with no feedings is discarded."""
        with self._con() as con:
            t = con.execute("SELECT bottle_id FROM feedings WHERE id = ? AND deleted = 0", (feeding_id,)).fetchone()
            if not t:
                return False
            con.execute("UPDATE feedings SET deleted = 1, modified_at = ? WHERE id = ?", (now_iso(), feeding_id))
            if t["bottle_id"]:
                b = self._bottle(con, t["bottle_id"])
                if b and b["n_feedings"] == 0 and b["closed_at"]:
                    con.execute("UPDATE bottles SET deleted = 1 WHERE id = ?", (b["id"],))
            return True

    def restore_feeding(self, feeding_id: int) -> bool:
        with self._con() as con:
            t = con.execute("SELECT bottle_id FROM feedings WHERE id = ? AND deleted = 1", (feeding_id,)).fetchone()
            if not t:
                return False
            con.execute("UPDATE feedings SET deleted = 0, modified_at = ? WHERE id = ?", (now_iso(), feeding_id))
            if t["bottle_id"]:
                con.execute("UPDATE bottles SET deleted = 0 WHERE id = ?", (t["bottle_id"],))
            return True

    def feedings_since(self, since_utc: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                "SELECT * FROM feedings WHERE deleted = 0 AND ended_at >= ? ORDER BY ended_at", (since_utc,)
            ).fetchall()
        return [dict(f) for f in rows]

    def feedings_range(self, since_utc: str, until_utc: str, deleted: bool = False) -> list[dict[str, Any]]:
        filter = "" if deleted else "deleted = 0 AND "
        with self._con() as con:
            rows = con.execute(
                f"SELECT * FROM feedings WHERE {filter}ended_at >= ? AND ended_at < ? ORDER BY ended_at",
                (since_utc, until_utc),
            ).fetchall()
        return [dict(f) for f in rows]

    def last_feeding(self) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM feedings WHERE deleted = 0 ORDER BY ended_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ diapers
    DIAPER_FIELDS = ("ended_at", "type", "color", "consistency", "note", "source", "logged_by")

    def add_diaper(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = [c for c in self.DIAPER_FIELDS if data.get(c) is not None]
        with self._con() as con:
            pid = con.execute(
                f"INSERT INTO diapers ({', '.join(fields)}, created_at) VALUES ({', '.join('?' * len(fields))}, ?)",
                [data[c] for c in fields] + [now_iso()],
            ).lastrowid
            return dict(con.execute("SELECT * FROM diapers WHERE id = ?", (pid,)).fetchone())

    def update_diaper(self, pid: int, changes: dict[str, Any]) -> dict[str, Any]:
        fields = [c for c in self.DIAPER_FIELDS if c in changes]
        with self._con() as con:
            if fields:
                cur = con.execute(
                    f"UPDATE diapers SET {', '.join(f'{c} = ?' for c in fields)}, modified_at = ? "
                    "WHERE id = ? AND deleted = 0",
                    [changes[c] for c in fields] + [now_iso(), pid],
                )
                if not cur.rowcount:
                    raise BabyError("diaper_not_found", id=pid)
            row = con.execute("SELECT * FROM diapers WHERE id = ? AND deleted = 0", (pid,)).fetchone()
        if not row:
            raise BabyError("diaper_not_found", id=pid)
        return dict(row)

    def delete_diaper(self, pid: int) -> bool:
        with self._con() as con:
            cur = con.execute(
                "UPDATE diapers SET deleted = 1, modified_at = ? WHERE id = ? AND deleted = 0", (now_iso(), pid)
            )
            return cur.rowcount > 0

    def diapers_range(self, since: str, until: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                "SELECT * FROM diapers WHERE deleted = 0 AND ended_at >= ? AND ended_at < ? ORDER BY ended_at", (since, until)
            ).fetchall()
        return [dict(f) for f in rows]

    def last_diaper(self, types: tuple[str, ...] = ("pee", "poop", "both")) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                f"SELECT * FROM diapers WHERE deleted = 0 AND type IN ({', '.join('?' * len(types))}) "
                "ORDER BY ended_at DESC, id DESC LIMIT 1", types,
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ developmental milestones
    def mark_milestone(self, milestone_id: str, date: str, note: str | None, user: str | None) -> dict[str, Any]:
        """Marks (or corrects) a milestone: `date` is the local day they noticed it (YYYY-MM-DD)."""
        now = now_iso()
        with self._con() as con:
            con.execute(
                "INSERT INTO milestones (milestone_id, date, note, logged_by, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(milestone_id) DO UPDATE SET date = excluded.date, note = excluded.note, "
                "logged_by = excluded.logged_by, modified_at = ?, deleted = 0",
                (milestone_id, date, note, user, now, now),
            )
            return dict(con.execute("SELECT * FROM milestones WHERE milestone_id = ?", (milestone_id,)).fetchone())

    def unmark_milestone(self, milestone_id: str) -> bool:
        with self._con() as con:
            cur = con.execute("UPDATE milestones SET deleted = 1, modified_at = ? WHERE milestone_id = ? AND deleted = 0",
                              (now_iso(), milestone_id))
            return cur.rowcount > 0

    def milestones(self) -> list[dict[str, Any]]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM milestones WHERE deleted = 0 ORDER BY date").fetchall()]

    # ------------------------------------------------------------ measurements
    def add_measurement(self, data: dict[str, Any]) -> int:
        fields = [
            c for c in ("date", "weight_kg", "height_cm", "head_cm", "note", "logged_by")
            if data.get(c) is not None
        ]
        sql = (
            f"INSERT INTO measurements ({', '.join(fields)}, created_at) "
            f"VALUES ({', '.join('?' * len(fields))}, ?)"
        )
        with self._con() as con:
            return con.execute(sql, [data[c] for c in fields] + [now_iso()]).lastrowid

    def measurements(self) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT * FROM measurements WHERE deleted = 0 ORDER BY date").fetchall()
        return [dict(f) for f in rows]

    def delete_measurement(self, measurement_id: int) -> bool:
        with self._con() as con:
            cur = con.execute("UPDATE measurements SET deleted = 1 WHERE id = ? AND deleted = 0", (measurement_id,))
            return cur.rowcount > 0

    def last_measurement(self, field: str) -> dict[str, Any] | None:
        """Latest measurement that has the given field (weight_kg, height_cm, head_cm)."""
        with self._con() as con:
            row = con.execute(
                f"SELECT * FROM measurements WHERE deleted = 0 AND {field} IS NOT NULL "
                "ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
