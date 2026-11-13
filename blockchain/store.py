"""SQLite storage for the Blockchain Intelligence Engine.

Default database: .local/regtest/engine.db (gitignored, local chain
data). Tests pass a temporary path instead.

Schema
------
blocks(height PK, hash UNIQUE, prev_hash, merkle_root, time,
       mediantime, nonce, bits, difficulty, chainwork, tx_count,
       size, weight, version, processed_at)
transactions(txid PK, block_hash, block_height, confirmations, size,
       vsize, weight, fee_sats NULL, vin_count, vout_count,
       first_seen, in_mempool)
sync_status(single row: tip_height, tip_hash, state, updated_at)
chain_events(id, ts, kind, detail)   kinds: new_block, reorg, sync

Reorganization safety: on a reorg, call invalidate_from(height). It
deletes block rows at and above the fork height and clears the block
assignment of transactions confirmed in them (they return to mempool
tracking rather than being deleted, since the transaction itself may
still be valid on the new branch).
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger("bal.blockchain.store")

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".local", "regtest", "engine.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY,
    hash TEXT UNIQUE NOT NULL,
    prev_hash TEXT,
    merkle_root TEXT,
    time INTEGER,
    mediantime INTEGER,
    nonce INTEGER,
    bits TEXT,
    difficulty REAL,
    chainwork TEXT,
    tx_count INTEGER,
    size INTEGER,
    weight INTEGER,
    version INTEGER,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    txid TEXT PRIMARY KEY,
    block_hash TEXT,
    block_height INTEGER,
    confirmations INTEGER,
    size INTEGER,
    vsize INTEGER,
    weight INTEGER,
    fee_sats INTEGER,
    vin_count INTEGER,
    vout_count INTEGER,
    first_seen TEXT,
    in_mempool INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sync_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    tip_height INTEGER,
    tip_hash TEXT,
    state TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS chain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    kind TEXT,
    detail TEXT
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


class BlockStore:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO sync_status (id, tip_height, tip_hash,"
            " state, updated_at) VALUES (1, -1, NULL, 'new', ?)", (_now(),))
        self.conn.commit()

    def close(self):
        self.conn.close()

    # Blocks
    def upsert_block(self, b):
        self.conn.execute(
            "INSERT INTO blocks (height, hash, prev_hash, merkle_root, time,"
            " mediantime, nonce, bits, difficulty, chainwork, tx_count, size,"
            " weight, version, processed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?) ON CONFLICT(height) DO UPDATE SET hash=excluded.hash,"
            " prev_hash=excluded.prev_hash, merkle_root=excluded.merkle_root,"
            " time=excluded.time, mediantime=excluded.mediantime,"
            " nonce=excluded.nonce, bits=excluded.bits,"
            " difficulty=excluded.difficulty, chainwork=excluded.chainwork,"
            " tx_count=excluded.tx_count, size=excluded.size,"
            " weight=excluded.weight, version=excluded.version,"
            " processed_at=excluded.processed_at",
            (b["height"], b["hash"], b.get("previousblockhash"),
             b.get("merkleroot"), b.get("time"), b.get("mediantime"),
             b.get("nonce"), b.get("bits"), b.get("difficulty"),
             b.get("chainwork"), len(b.get("tx", [])), b.get("size"),
             b.get("weight"), b.get("version"), _now()))
        self.conn.commit()

    def block_at_height(self, height):
        row = self.conn.execute(
            "SELECT * FROM blocks WHERE height = ?", (height,)).fetchone()
        return dict(row) if row else None

    def block_by_hash(self, blockhash):
        row = self.conn.execute(
            "SELECT * FROM blocks WHERE hash = ?", (blockhash,)).fetchone()
        return dict(row) if row else None

    def block_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]

    def latest_blocks(self, count):
        rows = self.conn.execute(
            "SELECT * FROM blocks ORDER BY height DESC LIMIT ?",
            (count,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def invalidate_from(self, height):
        """Drop blocks at and above height (reorg). Returns rows dropped."""
        cur = self.conn.execute(
            "DELETE FROM blocks WHERE height >= ?", (height,))
        self.conn.execute(
            "UPDATE transactions SET block_hash = NULL, block_height = NULL,"
            " confirmations = 0, in_mempool = 1 WHERE block_height >= ?",
            (height,))
        self.conn.commit()
        return cur.rowcount

    # Transactions
    def upsert_transaction(self, tx, block_hash=None, block_height=None,
                           in_mempool=False):
        self.conn.execute(
            "INSERT INTO transactions (txid, block_hash, block_height,"
            " confirmations, size, vsize, weight, fee_sats, vin_count,"
            " vout_count, first_seen, in_mempool) VALUES (?,?,?,?,?,?,?,?,?,"
            "?,?,?) ON CONFLICT(txid) DO UPDATE SET block_hash=excluded."
            "block_hash, block_height=excluded.block_height, confirmations="
            "excluded.confirmations, size=excluded.size, vsize=excluded."
            "vsize, weight=excluded.weight, fee_sats=excluded.fee_sats,"
            " vin_count=excluded.vin_count, vout_count=excluded.vout_count,"
            " in_mempool=excluded.in_mempool",
            (tx["txid"], block_hash, block_height, tx.get("confirmations", 0),
             tx.get("size"), tx.get("vsize"), tx.get("weight"),
             tx.get("fee_sats"), len(tx.get("vin", [])),
             len(tx.get("vout", [])), _now(), 1 if in_mempool else 0))
        self.conn.commit()

    def transaction(self, txid):
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE txid = ?", (txid,)).fetchone()
        return dict(row) if row else None

    def transaction_count(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transactions").fetchone()[0]

    # Sync status and events
    def set_sync(self, tip_height, tip_hash, state):
        self.conn.execute(
            "UPDATE sync_status SET tip_height = ?, tip_hash = ?, state = ?,"
            " updated_at = ? WHERE id = 1",
            (tip_height, tip_hash, state, _now()))
        self.conn.commit()

    def get_sync(self):
        row = self.conn.execute(
            "SELECT * FROM sync_status WHERE id = 1").fetchone()
        return dict(row)

    def record_event(self, kind, detail):
        if not isinstance(detail, str):
            detail = json.dumps(detail)
        self.conn.execute(
            "INSERT INTO chain_events (ts, kind, detail) VALUES (?,?,?)",
            (_now(), kind, detail))
        self.conn.commit()
        log.info("event %s: %s", kind, detail)

    def events(self, kind=None, limit=50):
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM chain_events WHERE kind = ? ORDER BY id DESC"
                " LIMIT ?", (kind, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM chain_events ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]
