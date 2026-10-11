from sqlalchemy import text

from app.database.session import engine

with engine.connect() as conn:
    version = conn.execute(text("select version()")).scalar()
    print("Connected to PostgreSQL:", version[:40])
    