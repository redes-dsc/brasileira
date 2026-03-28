from pathlib import Path

import psycopg

from newsroom_v3.config.settings import get_settings


def apply_migrations() -> None:
    settings = get_settings()
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))

    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            for file_path in files:
                sql_text = file_path.read_text(encoding="utf-8")
                cur.execute(sql_text)
                print(f"applied: {file_path.name}")
        conn.commit()


if __name__ == "__main__":
    apply_migrations()
