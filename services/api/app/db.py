from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import settings

engine: Engine = create_engine(settings.app_database_url, pool_pre_ping=True)


@contextmanager
def authorized_session(principal: Principal) -> Generator[Session, None, None]:
    """Open a transaction and apply authorization context only to that transaction."""
    with Session(engine) as session, session.begin():
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(principal.tenant_id)},
        )
        session.execute(
            text("SELECT set_config('app.subject_id', :subject_id, true)"),
            {"subject_id": str(principal.subject_id) if principal.subject_id else ""},
        )
        yield session

