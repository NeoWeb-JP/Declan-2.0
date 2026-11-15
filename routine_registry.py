"""Validated, persistent Home Assistant routine mappings.

No routine execution happens when mappings are created or imported.
"""
import json
import re
import sqlite3
import history

SCRIPT = re.compile(r"script\.[a-z0-9_]+\Z")
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
PHRASE = re.compile(r"[a-z0-9][a-z0-9 '\-]{0,119}\Z")
FIELD = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
RESERVED = {"morning", "night", "movie", "movie_bedroom"}
MAX_ROUTINES = 40

def validate(mapping):
    if not isinstance(mapping, dict) or len(mapping) > MAX_ROUTINES:
        raise ValueError("Invalid routine collection")
    clean = {}
    all_phrases = set()
    for name, item in mapping.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(item, dict):
            raise ValueError("Invalid routine name")
        if set(item) != {"script", "phrases", "fields", "sensitive"}:
            raise ValueError("Invalid routine definition")
        script, phrases, fields = item["script"], item["phrases"], item["fields"]
        if not isinstance(script, str) or not SCRIPT.fullmatch(script):
            raise ValueError("Select a Home Assistant script")
        if not isinstance(phrases, list) or not 1 <= len(phrases) <= 12:
            raise ValueError("Supply 1 to 12 phrases")
        if not isinstance(fields, dict) or len(fields) > 12:
            raise ValueError("Too many script fields")
        if type(item["sensitive"]) is not bool:
            raise ValueError("Invalid confirmation policy")
        for phrase in phrases:
            if not isinstance(phrase, str) or not PHRASE.fullmatch(phrase) or phrase != phrase.strip() or phrase in all_phrases:
                raise ValueError("Duplicate or invalid routine phrase")
            all_phrases.add(phrase)
        for key, value in fields.items():
            if not isinstance(key, str) or not FIELD.fullmatch(key) or not isinstance(value, (str, int, float, bool)) or len(str(value)) > 120:
                raise ValueError("Invalid script field")
            if isinstance(value, float) and (value != value or abs(value) > 1e9):
                raise ValueError("Invalid numeric field")
        clean[name] = {"script": script, "phrases": phrases, "fields": fields, "sensitive": item["sensitive"]}
    return clean

def load():
    with history.database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS routine_registry (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        row = db.execute("SELECT payload FROM routine_registry WHERE id=1").fetchone()
    return validate(json.loads(row[0])) if row else {}

def save(mapping):
    clean = validate(mapping)
    with history.database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS routine_registry (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO routine_registry (id,payload) VALUES (1,?)", (json.dumps(clean, sort_keys=True),))
    return clean

def match(phrase):
    for name, item in load().items():
        if phrase in item["phrases"]:
            return name, item
    return None
