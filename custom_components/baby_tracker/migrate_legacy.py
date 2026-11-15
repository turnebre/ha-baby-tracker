"""Import a database created by the previous, Spanish-language version of this integration.

The legacy file (``bebe.db`` / ``bebe_<id>.db``, schema v6) is never modified: it is copied with the SQLite
backup API and the copy is renamed table by table, column by column and value by value to the English schema.
This module intentionally keeps the old Spanish names, because they are the data being converted.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from .db import BabyDB

SUPPORTED_VERSIONS = (5, 6)  # v5 only lacks the `hitos` table (added in v6), which is created during import

# old table -> new table
TABLES = {
    "tomas": "feedings",
    "biberones": "bottles",
    "extracciones": "pumpings",
    "panales": "diapers",
    "medidas": "measurements",
    "hitos": "milestones",
}

# new table -> {old column: new column} (columns that keep their name are omitted)
COLUMNS = {
    "feedings": {
        "inicio": "started_at", "fin": "ended_at", "oz_preparadas": "oz_prepared", "oz_sobrantes": "oz_leftover",
        "oz_tomadas": "oz_taken", "tipo": "type", "confianza": "confidence", "fuente": "source",
        "registrado_por": "logged_by", "nota": "note", "creado": "created_at", "modificado": "modified_at",
        "borrado": "deleted", "biberon_id": "bottle_id",
    },
    "bottles": {
        "preparado": "prepared_at", "tipo": "type", "cerrado": "closed_at", "nota": "note", "creado": "created_at",
        "borrado": "deleted", "hecho": "made_at", "ubicacion": "location", "en_reserva": "in_stash",
        "extraccion_id": "pumping_id", "activado": "activated_at",
    },
    "pumpings": {
        "fin": "ended_at", "oz_izq": "oz_left", "oz_der": "oz_right", "duracion_min": "duration_min",
        "nota": "note", "registrado_por": "logged_by", "creado": "created_at", "borrado": "deleted",
    },
    "diapers": {
        "fin": "ended_at", "tipo": "type", "consistencia": "consistency", "nota": "note", "fuente": "source",
        "registrado_por": "logged_by", "creado": "created_at", "modificado": "modified_at", "borrado": "deleted",
    },
    "measurements": {
        "fecha": "date", "peso_kg": "weight_kg", "talla_cm": "height_cm", "perimetro_cm": "head_cm",
        "nota": "note", "registrado_por": "logged_by", "creado": "created_at", "borrado": "deleted",
    },
    "milestones": {
        "hito_id": "milestone_id", "fecha": "date", "nota": "note", "registrado_por": "logged_by",
        "creado": "created_at", "modificado": "modified_at", "borrado": "deleted",
    },
}

_TYPE = {"formula": "formula", "materna": "breast_milk", "mixta": "mixed"}
_SOURCE = {"boton": "button", "alexa": "alexa", "notificacion": "notification", "app": "app",
           "manual": "manual", "prueba": "test", "voz": "voice"}

# (new table, new column) -> {old value: new value}
VALUES = {
    ("feedings", "type"): _TYPE,
    ("bottles", "type"): _TYPE,
    ("feedings", "confidence"): {"exacto": "exact", "estimado": "estimated", "inferido": "inferred"},
    ("feedings", "source"): _SOURCE,
    ("diapers", "source"): _SOURCE,
    ("diapers", "type"): {"pipi": "pee", "popo": "poop", "ambos": "both"},
    ("diapers", "color"): {"amarillo": "yellow", "verde": "green", "cafe": "brown", "naranja": "orange",
                           "negro": "black", "rojo": "red", "blanco": "white", "no_se": "not_sure"},
    ("diapers", "consistency"): {"liquida": "watery", "grumosa": "seedy", "pastosa": "pasty", "dura": "hard",
                                 "no_se": "not_sure"},
    ("bottles", "location"): {"ambiente": "room", "refrigerador": "fridge"},
}

# old milestone step id -> new step id (the catalog in www/milestones.json uses the new ones)
MILESTONE_IDS = {
    "sonrie_respuesta": "smiles_in_response", "sonrie_solo": "smiles_on_own", "risita": "chuckles", "rie": "laughs",
    "rie_escondidas": "laughs_peekaboo", "se_calma": "calms_down", "mira_cara": "looks_at_face",
    "contento_verte": "happy_to_see_you", "busca_atencion": "seeks_attention", "reconoce": "knows_familiar_people",
    "timido": "shy_with_strangers", "reacciona_vas": "reacts_when_you_leave", "espejo": "likes_mirror",
    "gestos_cara": "facial_expressions", "juegos": "plays_games", "sonidos": "makes_sounds", "arrullos": "coos",
    "responde_sonidos": "sounds_back", "turnos": "takes_turns", "trompetillas": "raspberries", "chillidos": "squeals",
    "balbuceo": "babbles", "mama_papa": "says_mama_dada", "ruidos": "reacts_to_loud_sounds",
    "voltea_voz": "turns_to_voice", "su_nombre": "responds_to_name", "entiende_no": "understands_no",
    "brazos_arriba": "arms_up", "adios": "waves_bye", "te_sigue": "tracks_you", "mira_juguete": "looks_at_toy",
    "mira_manos": "looks_at_hands", "a_la_boca": "mouths_objects", "alcanza": "reaches_for_toy",
    "golpea": "bangs_things", "recipiente": "puts_in_container", "busca_caido": "looks_for_dropped",
    "busca_oculto": "looks_for_hidden", "abre_boca": "opens_mouth_for_food", "cierra_labios": "closes_lips_when_full",
    "cabeza_boca_abajo": "head_up_tummy", "codos": "pushes_up_elbows", "cabeza_firme": "head_steady",
    "brazos_rectos": "straight_arms", "mueve_todo": "moves_all_limbs", "abre_manos": "opens_hands",
    "manos_boca": "hands_to_mouth", "sostiene": "holds_toy", "manotea": "swats_toys",
    "cambia_mano": "passes_hand_to_hand", "rastrilla": "rakes_food", "pinza": "pincer_grasp",
    "vaso": "drinks_from_cup", "rueda": "rolls_over", "apoya_manos": "leans_on_hands", "sienta_solo": "sits_alone",
    "llega_sentado": "gets_to_sitting", "gatea": "crawls", "se_para": "pulls_to_stand",
    "camina_muebles": "cruises",
}

_LEGACY_NAME = re.compile(r"^bebe(_[0-9a-f]+)?\.db$")


class LegacyImportError(Exception):
    """The legacy database cannot be imported; `key` matches an error in translations/en.json."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def find_legacy_dbs(config_dir: str) -> list[str]:
    """File names of legacy databases (bebe.db, bebe_<id>.db) in the Home Assistant config folder."""
    try:
        return sorted(f for f in os.listdir(config_dir) if _LEGACY_NAME.match(f))
    except OSError:
        return []


def import_legacy_db(source: str, dest: str) -> None:
    """Copy `source` (legacy schema v5 or v6) to `dest` converted to the English schema. `source` is left untouched."""
    if os.path.exists(dest):
        raise LegacyImportError("import_destination_exists")
    if not os.path.isfile(source):
        raise LegacyImportError("import_failed")
    try:
        _convert(source, dest)
    except LegacyImportError:
        _remove(dest)
        raise
    except (sqlite3.Error, OSError) as err:
        _remove(dest)
        raise LegacyImportError("import_failed") from err


def _remove(path: str) -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(path + suffix).unlink(missing_ok=True)


def _convert(source: str, dest: str) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        if src.execute("PRAGMA user_version").fetchone()[0] not in SUPPORTED_VERSIONS:
            raise LegacyImportError("import_unsupported_version")
        names = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not set(TABLES) - {"hitos"} <= names:
            raise LegacyImportError("import_unsupported_version")
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    con = sqlite3.connect(dest, isolation_level=None)
    try:
        con.execute("BEGIN")
        con.execute(
            "CREATE TABLE IF NOT EXISTS hitos (hito_id TEXT PRIMARY KEY, fecha TEXT NOT NULL, nota TEXT, "
            "registrado_por TEXT, creado TEXT NOT NULL, modificado TEXT, borrado INTEGER NOT NULL DEFAULT 0)"
        )
        # Old index names are Spanish; the new schema recreates them below.
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx\\_%' ESCAPE '\\'").fetchall():
            con.execute(f'DROP INDEX "{name}"')
        for old, new in TABLES.items():
            con.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')
        for table, columns in COLUMNS.items():
            existing = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
            for old, new in columns.items():
                if old in existing:
                    con.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')
        for (table, column), mapping in VALUES.items():
            for old, new in mapping.items():
                con.execute(f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?', (new, old))
        for old, new in MILESTONE_IDS.items():
            con.execute("UPDATE milestones SET milestone_id = ? WHERE milestone_id = ?", (new, old))
        con.execute("PRAGMA user_version = 0")  # BabyDB.initialize() stamps the current version
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    BabyDB(dest).initialize()
