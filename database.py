import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


DATABASE_FILE = "jonah.sqlite3"
MIGRATIONS_DIRECTORY = Path(__file__).parent / "migrations"


def get_database_connection():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ---------------------------------------------------------------------
# Flyway-style database migrations
# ---------------------------------------------------------------------

def create_schema_history_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flyway_schema_history (
            version TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            script TEXT NOT NULL,
            installed_on TEXT NOT NULL
        )
        """
    )


def get_applied_migration_versions(connection):
    cursor = connection.execute(
        """
        SELECT version
        FROM flyway_schema_history
        """
    )

    return {row["version"] for row in cursor.fetchall()}


def parse_migration_file(migration_file):
    file_name = migration_file.name

    if not file_name.startswith("V") or "__" not in file_name or not file_name.endswith(".sql"):
        return None

    version_and_description = file_name[:-4]
    version_part, description_part = version_and_description.split("__", 1)

    version = version_part[1:]
    description = description_part.replace("_", " ")

    return {
        "version": version,
        "description": description,
        "script": file_name,
        "path": migration_file,
    }


def get_migration_files():
    if not MIGRATIONS_DIRECTORY.exists():
        MIGRATIONS_DIRECTORY.mkdir(parents=True)

    migrations = []

    for migration_file in MIGRATIONS_DIRECTORY.glob("V*__*.sql"):
        migration = parse_migration_file(migration_file)

        if migration is not None:
            migrations.append(migration)

    return sorted(migrations, key=lambda migration: migration["version"])


def apply_migration(connection, migration):
    sql = migration["path"].read_text(encoding="utf-8")

    connection.executescript(sql)

    connection.execute(
        """
        INSERT INTO flyway_schema_history (
            version,
            description,
            script,
            installed_on
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            migration["version"],
            migration["description"],
            migration["script"],
            datetime.utcnow().isoformat(),
        ),
    )

    print(
        f'Applied migration V{migration["version"]}: '
        f'{migration["description"]}'
    )


def run_database_migrations():
    connection = get_database_connection()

    try:
        with connection:
            create_schema_history_table(connection)

            applied_versions = get_applied_migration_versions(connection)
            migrations = get_migration_files()

            for migration in migrations:
                if migration["version"] not in applied_versions:
                    apply_migration(connection, migration)
    finally:
        connection.close()


# ---------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------

def hash_password(password):
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )

    return f"{salt.hex()}:{password_hash.hex()}"


def verify_password(password, stored_password):
    salt_hex, password_hash_hex = stored_password.split(":")
    salt = bytes.fromhex(salt_hex)
    expected_password_hash = bytes.fromhex(password_hash_hex)

    actual_password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )

    return actual_password_hash == expected_password_hash


# ---------------------------------------------------------------------
# Seed/default data
# ---------------------------------------------------------------------

def seed_player_if_empty():
    connection = get_database_connection()

    try:
        with connection:
            cursor = connection.execute("SELECT COUNT(*) AS player_count FROM player")
            player_count = cursor.fetchone()["player_count"]

            if player_count == 0:
                player_uuid = str(uuid.uuid4())

                connection.execute(
                    """
                    INSERT INTO player (
                        uuid,
                        name,
                        locationx,
                        locationy,
                        currentclass,
                        metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        player_uuid,
                        "First Player",
                        0,
                        0,
                        "adventurer",
                        json.dumps(
                            {
                                "life": 100,
                                "magic": 50,
                                "strength": 10,
                                "agility": 10,
                                "bless": 0,
                            }
                        ),
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO player_login (
                        player_uuid,
                        username,
                        password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        player_uuid,
                        "firstplayer",
                        hash_password("password"),
                    ),
                )

                print("Inserted default player.")
                print("Default login username: firstplayer")
                print("Default login password: password")
    finally:
        connection.close()


def username_exists(connection, username):
    cursor = connection.execute(
        """
        SELECT 1
        FROM player_login
        WHERE username = ?
        """,
        (username,),
    )

    return cursor.fetchone() is not None


def create_missing_login_for_existing_players():
    connection = get_database_connection()

    try:
        with connection:
            cursor = connection.execute(
                """
                SELECT
                    player.uuid,
                    player.name
                FROM player
                LEFT JOIN player_login
                    ON player.uuid = player_login.player_uuid
                WHERE player_login.player_uuid IS NULL
                """
            )

            players_without_login = cursor.fetchall()

            for player in players_without_login:
                username = player["name"].lower().replace(" ", "")
                base_username = username
                suffix = 1

                while username_exists(connection, username):
                    suffix += 1
                    username = f"{base_username}{suffix}"

                connection.execute(
                    """
                    INSERT INTO player_login (
                        player_uuid,
                        username,
                        password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        player["uuid"],
                        username,
                        hash_password("password"),
                    ),
                )

                print(
                    f'Created login for "{player["name"]}" '
                    f'with username "{username}" and default password "password".'
                )
    finally:
        connection.close()


def initialize_database():
    run_database_migrations()
    seed_player_if_empty()
    create_missing_login_for_existing_players()


# ---------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------

def get_players():
    connection = get_database_connection()

    try:
        cursor = connection.execute(
            """
            SELECT
                player.uuid,
                player.name,
                player.locationx,
                player.locationy,
                player.currentclass,
                player.metadata,
                player_login.username
            FROM player
            LEFT JOIN player_login
                ON player.uuid = player_login.player_uuid
            ORDER BY player.name
            """
        )

        players = []

        for row in cursor.fetchall():
            players.append(
                {
                    "uuid": row["uuid"],
                    "name": row["name"],
                    "username": row["username"],
                    "locationx": row["locationx"],
                    "locationy": row["locationy"],
                    "currentclass": row["currentclass"],
                    "metadata": json.loads(row["metadata"]),
                }
            )

        return players
    finally:
        connection.close()


def create_player(name, username, password, currentclass="adventurer"):
    player_uuid = str(uuid.uuid4())
    connection = get_database_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO player (
                    uuid,
                    name,
                    locationx,
                    locationy,
                    currentclass,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    player_uuid,
                    name,
                    0,
                    0,
                    currentclass,
                    json.dumps(
                        {
                            "life": 100,
                            "magic": 50,
                            "strength": 10,
                            "agility": 10,
                            "bless": 0,
                        }
                    ),
                ),
            )

            connection.execute(
                """
                INSERT INTO player_login (
                    player_uuid,
                    username,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (
                    player_uuid,
                    username,
                    hash_password(password),
                ),
            )

        return player_uuid
    finally:
        connection.close()


def create_player_with_zero_stats(name, username, password, currentclass="adventurer"):
    player_uuid = str(uuid.uuid4())
    connection = get_database_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO player (
                    uuid,
                    name,
                    locationx,
                    locationy,
                    currentclass,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    player_uuid,
                    name,
                    0,
                    0,
                    currentclass,
                    json.dumps(
                        {
                            "life": 0,
                            "magic": 0,
                            "strength": 0,
                            "agility": 0,
                            "bless": 0,
                        }
                    ),
                ),
            )

            connection.execute(
                """
                INSERT INTO player_login (
                    player_uuid,
                    username,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (
                    player_uuid,
                    username,
                    hash_password(password),
                ),
            )

        return get_player_by_login(username, password)
    finally:
        connection.close()


def get_player_by_login(username, password):
    connection = get_database_connection()

    try:
        cursor = connection.execute(
            """
            SELECT
                player.uuid,
                player.name,
                player.locationx,
                player.locationy,
                player.currentclass,
                player.metadata,
                player_login.username,
                player_login.password_hash
            FROM player
            INNER JOIN player_login
                ON player.uuid = player_login.player_uuid
            WHERE player_login.username = ?
            """,
            (username,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        if not verify_password(password, row["password_hash"]):
            return None

        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "username": row["username"],
            "locationx": row["locationx"],
            "locationy": row["locationy"],
            "currentclass": row["currentclass"],
            "metadata": json.loads(row["metadata"]),
        }
    finally:
        connection.close()


def get_player_by_username(username):
    connection = get_database_connection()

    try:
        cursor = connection.execute(
            """
            SELECT
                player.uuid,
                player.name,
                player.locationx,
                player.locationy,
                player.currentclass,
                player.metadata,
                player_login.username
            FROM player
            INNER JOIN player_login
                ON player.uuid = player_login.player_uuid
            WHERE player_login.username = ?
            """,
            (username,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "username": row["username"],
            "locationx": row["locationx"],
            "locationy": row["locationy"],
            "currentclass": row["currentclass"],
            "metadata": json.loads(row["metadata"]),
        }
    finally:
        connection.close()


def login_or_create_player(username, password):
    username = username.strip()

    if not username:
        return {
            "success": False,
            "message": "Username is required.",
            "player": None,
            "created": False,
        }

    if not password:
        return {
            "success": False,
            "message": "Password is required.",
            "player": None,
            "created": False,
        }

    existing_player = get_player_by_username(username)

    if existing_player is not None:
        logged_in_player = get_player_by_login(username, password)

        if logged_in_player is None:
            return {
                "success": False,
                "message": "Incorrect password for this username.",
                "player": None,
                "created": False,
            }

        return {
            "success": True,
            "message": "Login successful.",
            "player": logged_in_player,
            "created": False,
        }

    new_player = create_player_with_zero_stats(
        name=username,
        username=username,
        password=password,
    )

    return {
        "success": True,
        "message": "Account created successfully.",
        "player": new_player,
        "created": True,
    }


def get_player_by_uuid(player_uuid):
    connection = get_database_connection()

    try:
        cursor = connection.execute(
            """
            SELECT
                player.uuid,
                player.name,
                player.locationx,
                player.locationy,
                player.currentclass,
                player.metadata,
                player_login.username
            FROM player
            LEFT JOIN player_login
                ON player.uuid = player_login.player_uuid
            WHERE player.uuid = ?
            """,
            (player_uuid,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        username = row["username"]

        if username is None:
            username = row["name"]

        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "username": username,
            "locationx": row["locationx"],
            "locationy": row["locationy"],
            "currentclass": row["currentclass"],
            "metadata": json.loads(row["metadata"]),
        }
    finally:
        connection.close()


def create_oauth_player(name):
    player_uuid = str(uuid.uuid4())
    connection = get_database_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO player (
                    uuid,
                    name,
                    locationx,
                    locationy,
                    currentclass,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    player_uuid,
                    name,
                    0,
                    0,
                    "adventurer",
                    json.dumps(
                        {
                            "life": 0,
                            "magic": 0,
                            "strength": 0,
                            "agility": 0,
                            "bless": 0,
                        }
                    ),
                ),
            )

        return player_uuid
    finally:
        connection.close()


def login_or_create_oauth_player(provider, provider_user_id, email, name):
    display_name = name or email or f"{provider} user"

    connection = get_database_connection()

    try:
        with connection:
            cursor = connection.execute(
                """
                SELECT player_uuid
                FROM player_oauth_login
                WHERE provider = ?
                  AND provider_user_id = ?
                """,
                (provider, provider_user_id),
            )

            row = cursor.fetchone()

            if row is not None:
                player_uuid = row["player_uuid"]

                connection.execute(
                    """
                    UPDATE player_oauth_login
                    SET email = ?,
                        name = ?
                    WHERE provider = ?
                      AND provider_user_id = ?
                    """,
                    (email, display_name, provider, provider_user_id),
                )

                return {
                    "success": True,
                    "message": "OAuth login successful.",
                    "player": get_player_by_uuid(player_uuid),
                    "created": False,
                }

        player_uuid = create_oauth_player(display_name)

        connection = get_database_connection()

        with connection:
            connection.execute(
                """
                INSERT INTO player_oauth_login (
                    provider,
                    provider_user_id,
                    player_uuid,
                    email,
                    name,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    provider_user_id,
                    player_uuid,
                    email,
                    display_name,
                    datetime.utcnow().isoformat(),
                ),
            )

        return {
            "success": True,
            "message": "OAuth account created successfully.",
            "player": get_player_by_uuid(player_uuid),
            "created": True,
        }
    finally:
        connection.close()