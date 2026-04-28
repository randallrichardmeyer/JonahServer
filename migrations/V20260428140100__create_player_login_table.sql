CREATE TABLE IF NOT EXISTS player_login (
    player_uuid TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    FOREIGN KEY (player_uuid) REFERENCES player (uuid)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);