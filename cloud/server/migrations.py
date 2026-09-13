import logging

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


logger = logging.getLogger("cloud_migrations")


_ADDITIVE_COLUMNS = {
    "parcels": {
        "revision": "INTEGER NOT NULL DEFAULT 1",
    },
    "job_steps": {
        "planning_mode": "VARCHAR(24) NOT NULL DEFAULT 'edge'",
        "fallback_policy": "VARCHAR(32) NOT NULL DEFAULT 'deny'",
        "operation_config": "JSON NOT NULL DEFAULT '{}'",
        "machine_assignments": "JSON NOT NULL DEFAULT '{}'",
    },
    "edge_tasks": {
        "protocol_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
        "planning_mode": "VARCHAR(24) NOT NULL DEFAULT 'edge'",
        "fallback_policy": "VARCHAR(32) NOT NULL DEFAULT 'deny'",
        "plan_id": "VARCHAR(128)",
        "plan_revision": "INTEGER NOT NULL DEFAULT 0",
        "path_checksum": "VARCHAR(64)",
        "field_revision": "INTEGER NOT NULL DEFAULT 1",
        "field_checksum": "VARCHAR(64)",
        "coordinate_frame": "JSON NOT NULL DEFAULT '{}'",
        "operation_config": "JSON NOT NULL DEFAULT '{}'",
        "desired_state": "VARCHAR(32) NOT NULL DEFAULT 'running'",
        "last_dispatch_at": "FLOAT",
    },
}


def migrate_schema(engine: Engine) -> None:
    """Apply additive SQLite migrations needed by existing Cloud Box databases."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table, definitions in _ADDITIVE_COLUMNS.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in definitions.items():
                if name in existing:
                    continue
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
                )
                logger.info("Added column %s.%s", table, name)
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)"
        )
