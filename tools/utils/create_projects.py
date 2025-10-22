#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create/Update DefectDojo Product + AISTProject(+Versions) directly in PostgreSQL.

Расширения:
- Поддержка GIT_HASH и FILE_HASH версий из JSON.
- Для FILE_HASH: sha256(version) = sha256(архива), копирование архива в MEDIA_ROOT и
  проставление source_archive / source_archive_sha256.

Примеры JSON см. в описании выше.

Зависимости:
  pip install psycopg2-binary
"""

import argparse
import json
import os
import sys
import shutil
import hashlib
from datetime import datetime

import psycopg2
from psycopg2.extras import Json, RealDictCursor


# ---------- Константы / валидация ----------

GIT_HASH = "GIT_HASH"
FILE_HASH = "FILE_HASH"

def _now_utc():
    return datetime.utcnow()


# ---------- SLA & Product Type helpers (без изменений логики) ----------

def ensure_sla_config(conn, name="Default") -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM dojo_sla_configuration WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
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
                7, True,
                30, True,
                90, True,
                180, True
            ),
        )
        return cur.fetchone()[0]


def ensure_product_type(conn, name="AIST", description=None) -> int:
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, created, updated, product_id, supported_languages,
                   script_path, compilable, profile
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
                        profile: dict[str, str],
                        compilable: bool = False) -> int:
    now = _now_utc()
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
                       compilable = %s,
                       updated = %s,
                       profile = %s
                 WHERE id = %s
                """,
                (Json(supported_languages), script_path_abs, bool(compilable), now, Json(profile), target["id"]),
            )
            return int(target["id"])
        cur.execute(
            """
            INSERT INTO aist_aistproject
              (created, updated, product_id, supported_languages,
               script_path, compilable, profile)
            VALUES
              (%s, %s, %s,
               %s, %s, %s, %s)
            RETURNING id
            """,
            (now, now, product_id, Json(supported_languages), script_path_abs, bool(compilable), Json(profile)),
        )
        return int(cur.fetchone()[0])


# ---------- Вспомогательные функции для версий ----------

def _sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _store_archive(archive_path: str, media_root: str, project_id: int) -> str:
    """
    Копирует архив в MEDIA_ROOT по правилу, аналогичному FileField(upload_to):
      aist_versions/<project_id>/YYYY/MM/DD/<filename>
    Возвращает относительный путь (для записи в DB поле source_archive).
    """
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"archive not found: {archive_path}")
    dt = datetime.utcnow()
    rel_dir = os.path.join("aist_versions", str(project_id), f"{dt:%Y}", f"{dt:%m}", f"{dt:%d}")
    abs_dir = os.path.join(media_root, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    filename = os.path.basename(archive_path)
    dest_abs = os.path.join(abs_dir, filename)

    # если файл уже есть — перезапишем (deterministic)
    shutil.copy2(archive_path, dest_abs)
    rel_path = os.path.join(rel_dir, filename).replace("\\", "/")
    return rel_path


def _normalize_versions(item: dict) -> list[dict]:
    """
    Приводит поле версий к списку объектов единого вида:
    {
      "version_type": "GIT_HASH" | "FILE_HASH",
      "version": "<string>",             # только для GIT_HASH
      "archive_path": "<path>",          # только для FILE_HASH
      "description": "<str>",            # optional
      "metadata": { ... }                # optional
    }
    """
    raw = item.get("versions")
    if raw is None:
        raw = item.get("project_version")

    if raw is None:
        return []

    # 1) одиночная строка
    if isinstance(raw, (str, int)):
        return [{"version_type": GIT_HASH, "version": str(raw)}]

    # 2) список строк
    if isinstance(raw, list) and all(isinstance(v, (str, int)) for v in raw):
        return [{"version_type": GIT_HASH, "version": str(v)} for v in raw]

    # 3) список объектов (расширенный формат)
    if isinstance(raw, list) and all(isinstance(v, dict) for v in raw):
        norm = []
        for v in raw:
            vt = (v.get("version_type") or GIT_HASH).strip().upper()
            if vt not in (GIT_HASH, FILE_HASH):
                raise ValueError(f"Unsupported version_type: {vt}")
            obj = {
                "version_type": vt,
                "description": v.get("description") or "",
                "metadata": v.get("metadata") or {},
            }
            if vt == GIT_HASH:
                ver = (v.get("version") or "").strip()
                if not ver:
                    raise ValueError("GIT_HASH version requires 'version' field.")
                obj["version"] = ver
            else:
                ap = (v.get("archive_path") or "").strip()
                if not ap:
                    raise ValueError("FILE_HASH version requires 'archive_path' field.")
                obj["archive_path"] = ap
            norm.append(obj)
        return norm

    raise ValueError("Invalid 'versions'/'project_version' format.")


# ---------- AISTProjectVersion upsert ----------

def upsert_aist_project_version(conn, *, project_id: int,
                                version_type: str,
                                version: str,
                                description: str,
                                metadata: dict,
                                source_archive_rel: str | None,
                                source_archive_sha256: str | None) -> int:
    """
    Апсерт версии. Для FILE_HASH 'version' должен быть sha256 архива.
    """
    now = _now_utc()
    with conn.cursor() as cur:
        # update
        cur.execute(
            """
            UPDATE aist_aistprojectversion
               SET description = %s,
                   metadata = %s,
                   updated = %s,
                   version_type = %s,
                   source_archive = %s,
                   source_archive_sha256 = %s
             WHERE project_id = %s AND version = %s
         RETURNING id
            """,
            (description or "", Json(metadata or {}), now,
             version_type, source_archive_rel, source_archive_sha256,
             project_id, version),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])

        # insert
        cur.execute(
            """
            INSERT INTO aist_aistprojectversion
              (project_id, version, description, metadata, created, updated,
               version_type, source_archive, source_archive_sha256)
            VALUES
              (%s, %s, %s, %s, %s, %s,
               %s, %s, %s)
            RETURNING id
            """,
            (project_id, version, description or "", Json(metadata or {}), now, now,
             version_type, source_archive_rel, source_archive_sha256),
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


def process(conn, json_path: str, product_type_name: str, sla_name: str, media_root: str | None) -> None:
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

        # 2) AISTProject (UPDATE-if-exists by product_id)
        proj_id = ensure_aist_project(
            conn,
            product_id=product_id,
            supported_languages=languages,
            script_path_abs=rel_script_path,
            compilable=compilable,
            profile=item.get("profile") or {},
        )
        print(f"[AISTProject] product_id={product_id} -> id={proj_id}")

        # 3) Versions
        versions = _normalize_versions(item)
        for entry in versions:
            vt = entry["version_type"]
            if vt == GIT_HASH:
                ver = entry["version"]
                ver_id = upsert_aist_project_version(
                    conn,
                    project_id=proj_id,
                    version_type=GIT_HASH,
                    version=ver,
                    description=entry.get("description") or description,
                    metadata=entry.get("metadata") or {},
                    source_archive_rel=None,
                    source_archive_sha256=None,
                )
                print(f"  [AISTProjectVersion] GIT_HASH {ver} -> id={ver_id}")
            else:
                # FILE_HASH
                if not media_root:
                    raise ValueError("FILE_HASH requires --media-root to copy archive into.")
                src = entry["archive_path"]
                sha = _sha256_of_file(src)
                rel_path = _store_archive(src, media_root, proj_id)
                ver_id = upsert_aist_project_version(
                    conn,
                    project_id=proj_id,
                    version_type=FILE_HASH,
                    version=sha,  # имя версии = sha256 архива
                    description=entry.get("description") or description,
                    metadata=entry.get("metadata") or {},
                    source_archive_rel=rel_path,
                    source_archive_sha256=sha,
                )
                print(f"  [AISTProjectVersion] FILE_HASH {sha} <- {src} -> {rel_path} -> id={ver_id}")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Upsert DefectDojo Product + AISTProject(+Versions) directly in PostgreSQL (supports GIT_HASH/FILE_HASH)."
    )
    parser.add_argument("--json", required=True, help="Path to projects.json")

    # DB args (respect PG* envs as defaults)
    parser.add_argument("--db-host", default=os.getenv("PGHOST", "127.0.0.1"))
    parser.add_argument("--db-port", default=os.getenv("PGPORT", "5432"))
    parser.add_argument("--db-name", default=os.getenv("PGDATABASE", "defectdojo"))
    parser.add_argument("--db-user", default=os.getenv("PGUSER", "defectdojo"))
    parser.add_argument("--db-pass", default=os.getenv("PGPASSWORD", "defectdojo"))

    # reference data names
    parser.add_argument("--product-type-name", default="AIST")
    parser.add_argument("--sla-name", default="Default")

    # где хранить загруженные архивы FILE_HASH
    parser.add_argument("--media-root", default=os.getenv("MEDIA_ROOT", None),
                        help="Absolute path to MEDIA_ROOT for storing version archives (required for FILE_HASH).")

    args = parser.parse_args()

    if not os.path.exists(args.json):
        print(f"projects.json not found: {args.json}", file=sys.stderr)
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
        process(conn, args.json, args.product_type_name, args.sla_name, args.media_root)
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
