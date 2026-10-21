"""The issuance record: one row of identifiers per 200, never a credential body, in a `gateway` schema in
Certify's Postgres. The search and revoke endpoints over it are the admin API's (a later task)."""

from __future__ import annotations

import psycopg


class Store:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS gateway")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS gateway.issuances (
                       id BIGSERIAL PRIMARY KEY,
                       sub TEXT NOT NULL,
                       credential_type TEXT NOT NULL,
                       scope TEXT NOT NULL,
                       client_id TEXT,
                       issued_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
            )

    def record(self, sub: str, credential_type: str, scope: str, client_id: str | None) -> None:
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            conn.execute(
                "INSERT INTO gateway.issuances (sub, credential_type, scope, client_id) VALUES (%s, %s, %s, %s)",
                (sub, credential_type, scope, client_id),
            )
