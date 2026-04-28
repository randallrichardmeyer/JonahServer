CREATE TABLE IF NOT EXISTS player (
    uuid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    locationx REAL NOT NULL DEFAULT 0,
    locationy REAL NOT NULL DEFAULT 0,
    currentclass TEXT NOT NULL,
    metadata TEXT NOT NULL
);