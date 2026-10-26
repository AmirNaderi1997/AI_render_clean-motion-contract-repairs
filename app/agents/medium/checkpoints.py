"""Official durable checkpointers. Same PostgreSQL database in production."""
from contextlib import contextmanager
from app import studio_store


def available():
    try:
        import langgraph.graph  # noqa: F401
        if studio_store.DB_AVAILABLE:
            import langgraph.checkpoint.postgres  # noqa: F401
        else:
            import langgraph.checkpoint.sqlite  # noqa: F401
    except ImportError as exc:
        raise ValueError("EditorGPT Medium در این نصب فعال نیست. وابستگی‌های Medium را نصب کنید یا خودتان EditorGPT Lite را انتخاب کنید.") from exc


@contextmanager
def saver():
    available()
    if studio_store.DB_AVAILABLE:
        from langgraph.checkpoint.postgres import PostgresSaver
        from app.config import settings
        # Engine URL is backend-owned; never accept a connection string from a client.
        url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        with PostgresSaver.from_conn_string(url) as checkpoint:
            yield checkpoint  # setup is a deployment migration, not a per-request DDL operation
    else:
        from langgraph.checkpoint.sqlite import SqliteSaver
        studio_store.ROOT.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(studio_store.ROOT / "medium-checkpoints.sqlite")) as checkpoint:
            yield checkpoint


def setup():
    with saver() as checkpoint:
        checkpoint.setup()


if __name__ == "__main__":
    setup()
    print("Medium checkpoint schema is ready.")
