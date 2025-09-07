#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create/Update DefectDojo Product + AISTProject(+Versions) directly in PostgreSQL.

- Reads projects from JSON (default: <root>/projects.json).
- Resolves script_path as ABS(--root) + JSON["script_path"].
- Product upserted by unique name with important fields set explicitly.
- AISTProject updated if exists for product_id (one per product). If multiple
  legacy rows exist, updates the most recently updated and prints a warning.
- AISTProjectVersion upserted by (project_id, version).
- No Django imports; uses psycopg2 transactions.

Requirements:
  pip install psycopg2-binary
"""

import argparse
import json
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import Json, RealDictCursor


# ---------- SLA & Product Type helpers ----------

def ensure_sla_config(conn, name="Default") -> int:
    """Ensure an SLA_Configuration exists; return its id."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM dojo_sla_configuration WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]

        # Reasonable defaults aligned with typical DefectDojo expectations
        cur.execute(
            """
            INSERT INTO dojo_sla_configuration
              (name, description,
               critical, enforce_critical,
               high, enforce_high,
               medium, enforce_medium,
               low, enforce_low,
               async_updating)
            VALUES
              (%s, %s,
               %s, %s,
               %s, %s,
               %s, %s,
               %s, %s,
               FALSE)
            RETURNING id
            """,
            (
                name, None,
                7, True,      # critical
                30, True,     # high
                90, True,     # medium
                180, True     # low
            ),
        )
        return cur.fetchone()[0]


def ensure_product_type(conn, name="AIST", description=None) -> int:
    """Ensure a Product_Type row exists; return its id."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM dojo_product_type WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE dojo_product_type
                   SET description = %s,
                       critical_product = COALESCE(critical_product, FALSE),
                       key_product = COALESCE(key_product, FALSE),
                       updated = NOW()
                 WHERE id = %s
                """,
                (description, row[0]),
            )
            return row[0]

        cur.execute(
            """
            INSERT INTO dojo_product_type
              (name, description, critical_product, key_product, created, updated)
            VALUES (%s, %s, FALSE, FALSE, NOW(), NOW())
            RETURNING id
            """,
            (name, description),
        )
        return cur.fetchone()[0]


# ---------- Product helpers ----------

def get_product_id_by_name(conn, name: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM dojo_product WHERE name=%s", (name,))
        r = cur.fetchone()
        return r[0] if r else None


def ensure_product(conn, *, name: str, description: str, prod_type_id: int, sla_config_id: int) -> int:
    """
    Upsert Product by unique name.
    Explicitly sets boolean fields that are NOT NULL in DB schemas to avoid NULL violations.
    Also sets tid=0 and timestamps for explicitness.
    """
    with conn.cursor() as cur:
        pid = get_product_id_by_name(conn, name)
        if pid:
            cur.execute(
                """
                UPDATE dojo_product
                   SET description = %s,
                       prod_type_id = %s,
                       sla_configuration_id = %s,
                       external_audience = FALSE,
                       internet_accessible = FALSE,
                       enable_product_tag_inheritance = FALSE,
                       enable_simple_risk_acceptance = FALSE,
                       enable_full_risk_acceptance = TRUE,
                       disable_sla_breach_notifications = FALSE,
                       async_updating = FALSE,
                       tid = COALESCE(tid, 0),
                       updated = NOW()
                 WHERE id = %s
                """,
                (description, prod_type_id, sla_config_id, pid),
            )
            return pid

        # Insert new product
        cur.execute(
            """
            INSERT INTO dojo_product
               (name, description, created, updated, prod_type_id,
                sla_configuration_id, tid,
                business_criticality, platform, lifecycle, origin, user_records, revenue,
                external_audience, internet_accessible, enable_product_tag_inheritance,
                enable_simple_risk_acceptance, enable_full_risk_acceptance,
                disable_sla_breach_notifications, async_updating)
            VALUES
               (%s, %s, NOW(), NOW(), %s,
                %s, 0,
                NULL, NULL, NULL, NULL, NULL, NULL,
                FALSE, FALSE, FALSE,
                FALSE, TRUE,
                FALSE, FALSE)
            RETURNING id
            """,
            (name, description, prod_type_id, sla_config_id),
        )
        return cur.fetchone()[0]


# ---------- AISTProject helpers (UPDATE-if-exists by product_id) ----------

def select_aist_projects_for_product(conn, product_id: int) -> list[dict]:
    """Return list of AISTProject rows for this product (could be >1 in legacy DBs)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, created, updated, product_id, supported_languages,
                   script_path, output_dir, compilable
              FROM aist_aistproject
             WHERE product_id = %s
             ORDER BY updated DESC NULLS LAST, id DESC
            """,
            (product_id,),
        )
        return cur.fetchall()


def ensure_aist_project(conn, *, product_id: int,
                        supported_languages: list[str],
                        script_path_abs: str,
                        output_dir: str = "/tmp/aist-output",
                        compilable: bool = False) -> int:
    """
    UPDATE-if-exists semantics by product_id:
      - If one or more AISTProject rows exist for this product, update the most recently updated one.
      - If none exist, insert a new row.
    Always sets 'updated'. On insert sets both 'created' and 'updated'.
    """
    now = datetime.utcnow()
    rows = select_aist_projects_for_product(conn, product_id)

    with conn.cursor() as cur:
        if rows:
            target = rows[0]
            if len(rows) > 1:
                print(f"[WARN] Product {product_id} has {len(rows)} AISTProject rows; updating the most recent id={target['id']}.")

            cur.execute(
                """
                UPDATE aist_aistproject
                   SET supported_languages = %s,
                       script_path = %s,
                       output_dir = %s,
                       compilable = %s,
                       updated = %s
                 WHERE id = %s
                """,
                (Json(supported_languages), script_path_abs, output_dir, bool(compilable), now, target["id"]),
            )
            return int(target["id"])

        # No existing project -> insert one
        cur.execute(
            """
            INSERT INTO aist_aistproject
              (created, updated, product_id, supported_languages,
               script_path, output_dir, compilable)
            VALUES
              (%s, %s, %s, %s,
               %s, %s, %s)
            RETURNING id
            """,
            (now, now, product_id, Json(supported_languages), script_path_abs, output_dir, bool(compilable)),
        )
        return int(cur.fetchone()[0])


# ---------- AISTProjectVersion helper ----------

def ensure_aist_project_version(conn, *, project_id: int, version: str,
                                description: str = "", metadata: dict | None = None) -> int:
    """Upsert version by (project_id, version)."""
    metadata = metadata or {}
    now = datetime.utcnow()
    with conn.cursor() as cur:
        # Try update first
        cur.execute(
            """
            UPDATE aist_aistprojectversion
               SET description = %s,
                   metadata = %s,
                   updated = %s
             WHERE project_id = %s AND version = %s
         RETURNING id
            """,
            (description or "", Json(metadata), now, project_id, version),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])

        # Insert new
        cur.execute(
            """
            INSERT INTO aist_aistprojectversion
              (project_id, version, description, metadata, created, updated)
            VALUES
              (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, version, description or "", Json(metadata), now, now),
        )
        return int(cur.fetchone()[0])


# ---------- Orchestration ----------

def load_projects(json_path: str) -> list[dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "projects" in data and isinstance(data["projects"], list):
        return data["projects"]
    if isinstance(data, list):
        return data
    raise ValueError("Invalid JSON format: expected {'projects': [...]} or a list [...]")


def process(conn, json_path: str, product_type_name: str, sla_name: str) -> None:
    projects = load_projects(json_path)
    sla_id = ensure_sla_config(conn, name=sla_name)
    pt_id = ensure_product_type(conn, name=product_type_name, description=None)

    for item in projects:
        name = (item.get("name") or "").strip()
        if not name:
            print("[WARN] Skipping item without 'name'")
            continue

        description = (item.get("description") or name).strip()
        languages = item.get("languages") or []
        if not isinstance(languages, list):
            raise ValueError(f"'languages' for {name} must be a list")
        compilable = bool(item.get("compilable", False))

        rel_script_path = (item.get("script_path") or "").strip()
        if not rel_script_path:
            print(f"[WARN] Skipping '{name}': no 'script_path'")
            continue

        # 1) Product
        product_id = ensure_product(
            conn,
            name=name,
            description=description,
            prod_type_id=pt_id,
            sla_config_id=sla_id,
        )
        print(f"[Product] name='{name}' -> id={product_id}")

        # 2) AISTProject (UPDATE-if-exists by product_id!)
        proj_id = ensure_aist_project(
            conn,
            product_id=product_id,
            supported_languages=languages,
            script_path_abs=rel_script_path,
            output_dir=item.get("output_dir", "/tmp/aist-output"),
            compilable=compilable,
        )
        print(f"[AISTProject] product_id={product_id} -> id={proj_id}")

        # 3) Versions
        versions = item.get("project_version") or []
        if isinstance(versions, (str, int)):
            versions = [str(versions)]
        else:
            versions = [str(v) for v in versions]

        for ver in versions:
            ver_id = ensure_aist_project_version(
                conn,
                project_id=proj_id,
                version=ver,
                description=description,
                metadata={},
            )
            print(f"  [AISTProjectVersion] {ver} -> id={ver_id}")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Upsert DefectDojo Product + AISTProject(+Versions) directly in PostgreSQL (no Django)."
    )
    parser.add_argument("--json", default=None,
                        help="Path to projects.json (default: <root>/projects.json).")

    # DB args (respect PG* envs as defaults)
    parser.add_argument("--db-host", default=os.getenv("PGHOST", "127.0.0.1"))
    parser.add_argument("--db-port", default=os.getenv("PGPORT", "5432"))
    parser.add_argument("--db-name", default=os.getenv("PGDATABASE", "defectdojo"))
    parser.add_argument("--db-user", default=os.getenv("PGUSER", "defectdojo"))
    parser.add_argument("--db-pass", default=os.getenv("PGPASSWORD", "defectdojo"))

    # reference data names
    parser.add_argument("--product-type-name", default="AIST")
    parser.add_argument("--sla-name", default="Default")

    args = parser.parse_args()

    json_path = args.json
    if not os.path.exists(json_path):
        print(f"projects.json not found: {json_path}", file=sys.stderr)
        sys.exit(2)

    conn = None
    try:
        conn = psycopg2.connect(
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=args.db_pass,
        )
        conn.autocommit = False
        process(conn, json_path, args.product_type_name, args.sla_name)
        conn.commit()
        print("Done.")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
