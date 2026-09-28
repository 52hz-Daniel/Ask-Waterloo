import argparse
import time
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import settings
from app.db import authorized_session
from app.telemetry import emit_event, trace_id_var


def process_once() -> int:
    # Tenant IDs are non-private configuration boundaries. Each tenant transaction
    # gets a fresh local RLS context; the worker never uses an all-tenant bypass role.
    discovery = create_engine(settings.app_database_url)
    with Session(discovery) as session:
        tenant_ids = list(session.execute(text("SELECT id FROM tenants")).scalars())
    processed = 0
    for tenant_id in tenant_ids:
        tenant_principal = Principal(UUID(str(tenant_id)), None, "worker", "worker-v1")
        with authorized_session(tenant_principal) as session:
            rows = list(
                session.execute(
                    text(
                        """SELECT id, event_type, trace_id FROM outbox_events
                        WHERE processed_at IS NULL ORDER BY created_at
                        FOR UPDATE SKIP LOCKED LIMIT 25"""
                    )
                ).mappings()
            )
            for row in rows:
                token = trace_id_var.set(row["trace_id"])
                try:
                    # This skeleton performs no external side effect. Durable state,
                    # bounded claims, retry count, and trace continuity are exercised.
                    session.execute(
                        text(
                            """UPDATE outbox_events SET processed_at = now(),
                            attempts = attempts + 1 WHERE id = :id"""
                        ),
                        {"id": row["id"]},
                    )
                    emit_event(
                        "outbox.processed", event_type=row["event_type"], attempt=1
                    )
                    processed += 1
                finally:
                    trace_id_var.reset(token)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll", action="store_true")
    args = parser.parse_args()
    while True:
        process_once()
        if not args.poll:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()

