CREATE TABLE IF NOT EXISTS player_oauth_login (
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    player_uuid TEXT NOT NULL,
    email TEXT,
    name TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id),
    FOREIGN KEY (player_uuid) REFERENCES player (uuid)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);