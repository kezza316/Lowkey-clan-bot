import sqlite3

conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL,
    total_level INTEGER DEFAULT 0
)
""")

conn.commit()


def add_player(discord_id, rsn):
    cursor.execute(
        "INSERT OR REPLACE INTO players (discord_id, rsn) VALUES (?, ?)",
        (discord_id, rsn),
    )
    conn.commit()


def get_players():
    cursor.execute("SELECT discord_id, rsn FROM players")
    return cursor.fetchall()


def update_level(discord_id, level):
    cursor.execute(
        "UPDATE players SET total_level=? WHERE discord_id=?",
        (level, discord_id),
    )
    conn.commit()
