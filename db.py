import sqlite3

conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

# Players table
cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL
)
""")

# Admin logs table
cursor.execute("""
CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT,
    target TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


# -------------------
# PLAYER FUNCTIONS
# -------------------
def add_player(discord_id, rsn):
    cursor.execute(
        "INSERT OR REPLACE INTO players VALUES (?, ?)",
        (discord_id, rsn)
    )
    conn.commit()


def remove_player(discord_id):
    cursor.execute("DELETE FROM players WHERE discord_id = ?", (discord_id,))
    conn.commit()


def get_players():
    cursor.execute("SELECT discord_id, rsn FROM players")
    return cursor.fetchall()


# -------------------
# ADMIN LOGGING
# -------------------
def log_admin(admin_id, action, target=""):
    cursor.execute(
        "INSERT INTO admin_logs (admin_id, action, target) VALUES (?, ?, ?)",
        (admin_id, action, target)
    )
    conn.commit()


def get_admin_logs(limit=10):
    cursor.execute("""
        SELECT admin_id, action, target, timestamp
        FROM admin_logs
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()
