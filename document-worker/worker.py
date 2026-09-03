"""Single-concurrency, persistent PDF/EPUB worker for Concat Notes."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import posixpath
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pymupdf as fitz
import psycopg
import requests
import pytesseract
from bs4 import BeautifulSoup
from botocore.client import Config
from ebooklib import epub, ITEM_DOCUMENT, ITEM_IMAGE
from PIL import Image
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [document-worker] %(levelname)s %(message)s")
logger = logging.getLogger("document-worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://notes_user:notes_password@db:5432/notes_db")
S3_ENDPOINT = os.getenv("RUSTFS_ENDPOINT_INTERNAL", "http://rustfs:9000")
S3_EXTERNAL = os.getenv("RUSTFS_ENDPOINT_EXTERNAL", "http://localhost:9000")
S3_BUCKET = os.getenv("RUSTFS_BUCKET_NAME", "notes-images")
S3_ACCESS = os.getenv("RUSTFS_ACCESS_KEY", "rustfs_admin")
S3_SECRET = os.getenv("RUSTFS_SECRET_KEY", "rustfs_password")
POLL_SECONDS = float(os.getenv("DOCUMENT_WORKER_POLL_SECONDS", "2"))
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def s3():
    return boto3.client("s3", endpoint_url=S3_ENDPOINT, aws_access_key_id=S3_ACCESS,
                        aws_secret_access_key=S3_SECRET, config=Config(signature_version="s3v4"), region_name="us-east-1")


def public_url(key: str) -> str:
    return f"{S3_EXTERNAL}/{S3_BUCKET}/{key}"


def upload(key: str, payload: bytes, media_type: str) -> None:
    s3().put_object(Bucket=S3_BUCKET, Key=key, Body=payload, ContentType=media_type)


def claim_job() -> dict[str, Any] | None:
    with db() as conn, conn.transaction():
        row = conn.execute(
            "SELECT * FROM document_jobs WHERE status='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if not row:
            return None
        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE document_jobs SET status='running', stage='starting', progress=1, message='Iniciando trabajo local', "
            "heartbeat_at=%s, started_at=COALESCE(started_at,%s), attempt=attempt+1 WHERE id=%s",
            (now, now, row["id"]),
        )
        return row


def update_job(job_id, *, stage: str, progress: int, message: str, warnings=None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE document_jobs SET stage=%s, progress=%s, message=%s, heartbeat_at=%s, warnings=COALESCE(%s,warnings) WHERE id=%s",
            (stage, max(0, min(100, progress)), message, datetime.now(timezone.utc), Jsonb(warnings) if warnings is not None else None, job_id),
        )
        conn.commit()


def cancelled(job_id) -> bool:
    with db() as conn:
        row = conn.execute("SELECT cancel_requested FROM document_jobs WHERE id=%s", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])


def finish(job_id, status: str, message: str, error: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE document_jobs SET status=%s, stage=%s, progress=%s, message=%s, error=%s, heartbeat_at=%s, finished_at=%s WHERE id=%s",
            (status, status, 100 if status == "completed" else 0, message, error, datetime.now(timezone.utc), datetime.now(timezone.utc), job_id),
        )
        conn.commit()


def local_copy(storage_key: str, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    s3().download_file(S3_BUCKET, storage_key, handle.name)
    return Path(handle.name)


def close_ranges(entries: list[dict[str, Any]], page_count: int) -> None:
    for index, entry in enumerate(entries):
        end = page_count
        for candidate in entries[index + 1:]:
            if candidate["level"] <= entry["level"]:
                end = max(entry["page_start"], candidate["page_start"] - 1)
                break
        entry["page_end"] = end


def pdf_sections(document: fitz.Document) -> tuple[list[dict[str, Any]], str]:
    toc = document.get_toc(simple=True)
    entries = []
    source = "pdf_outline"
    if toc:
        for index, (level, title, page) in enumerate(toc):
            if page < 1 or page > document.page_count:
                continue
            entries.append({"key": index, "level": max(1, level), "title": title.strip() or f"Sección {index + 1}", "page_start": page})
    if not entries:
        source = "pdf_heading"
        candidates = []
        for page_index in range(document.page_count):
            page = document[page_index]
            blocks = page.get_text("dict").get("blocks", [])
            spans = [span for block in blocks for line in block.get("lines", []) for span in line.get("spans", []) if span.get("text", "").strip()]
            body_sizes = sorted(span.get("size", 0) for span in spans)
            body = body_sizes[len(body_sizes) // 2] if body_sizes else 10
            for span in spans:
                text = " ".join(span.get("text", "").split())
                if 3 <= len(text) <= 160 and span.get("size", 0) >= body * 1.35:
                    candidates.append({"level": 1 if span.get("size", 0) >= body * 1.7 else 2, "title": text, "page_start": page_index + 1})
                    break
        seen = set()
        for item in candidates:
            identity = (item["title"].casefold(), item["page_start"])
            if identity not in seen:
                item["key"] = len(entries)
                entries.append(item)
                seen.add(identity)
    if not entries:
        source = "synthetic"
        for start in range(1, document.page_count + 1, 20):
            entries.append({"key": len(entries), "level": 1, "title": f"Páginas {start}-{min(start + 19, document.page_count)}", "page_start": start})
    close_ranges(entries, document.page_count)
    return entries, source


def persist_sections(document_id, entries: list[dict[str, Any]], source: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM document_sections WHERE document_id=%s", (document_id,))
        stack: list[tuple[int, uuid.UUID]] = []
        for index, item in enumerate(entries):
            while stack and stack[-1][0] >= item["level"]:
                stack.pop()
            section_id = uuid.uuid4()
            parent_id = stack[-1][1] if stack else None
            conn.execute(
                "INSERT INTO document_sections(id,document_id,parent_id,order_index,level,title,source_kind,page_start,page_end,epub_href,fragment_id,confidence) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (section_id, document_id, parent_id, index, item["level"], item["title"], source,
                 item.get("page_start"), item.get("page_end"), item.get("href"), item.get("fragment"), item.get("confidence", 1.0)),
            )
            stack.append((item["level"], section_id))
        conn.commit()


def inspect_pdf(job: dict[str, Any], document: dict[str, Any], path: Path) -> None:
    pdf = fitz.open(path)
    if pdf.page_count > 1000:
        raise ValueError("El PDF supera el límite de 1000 páginas.")
    update_job(job["id"], stage="detecting_structure", progress=20, message=f"Inspeccionando {pdf.page_count} páginas")
    sections, source = pdf_sections(pdf)
    persist_sections(document["id"], sections, source)
    native_pages = 0
    visual_count = 0
    low_text = []
    for index, page in enumerate(pdf):
        chars = len(page.get_text("text").strip())
        native_pages += chars >= 80
        if chars < 30:
            low_text.append(index + 1)
        visual_count += len(page.get_images(full=True))
        if index < 30:
            pix = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            out = io.BytesIO(); image.save(out, format="WEBP", quality=65)
            key = f"documents/{document['id']}/thumbnails/page-{index + 1}.webp"
            upload(key, out.getvalue(), "image/webp")
            with db() as conn:
                conn.execute(
                    "INSERT INTO document_assets(id,document_id,storage_key,media_type,kind,page_number,content_hash,width,height) "
                    "VALUES(%s,%s,%s,'image/webp','thumbnail',%s,%s,%s,%s) ON CONFLICT(storage_key) DO NOTHING",
                    (uuid.uuid4(), document["id"], key, index + 1, hashlib.sha256(out.getvalue()).hexdigest(), image.width, image.height),
                ); conn.commit()
    metadata = pdf.metadata or {}
    capabilities = {"sections": True, "pages": True, "native_text_pages": native_pages,
                    "low_text_pages": low_text, "visual_candidates": visual_count, "thumbnail_pages": min(30, pdf.page_count)}
    warnings = []
    if low_text:
        warnings.append(f"{len(low_text)} páginas tienen poco texto nativo y pueden requerir OCR.")
    with db() as conn:
        conn.execute(
            "UPDATE source_documents SET page_count=%s,title=%s,author=%s,parser_name='PyMuPDF',parser_version=%s,status='ready',capabilities=%s,warnings=%s,updated_at=%s WHERE id=%s",
            (pdf.page_count, metadata.get("title") or document["title"], metadata.get("author") or "", fitz.VersionBind,
             Jsonb(capabilities), Jsonb(warnings), datetime.now(timezone.utc), document["id"]),
        ); conn.commit()


def flatten_epub_toc(items, level=1, result=None):
    result = result if result is not None else []
    for item in items:
        if isinstance(item, tuple):
            section, children = item
            result.append({"level": level, "title": getattr(section, "title", "Sección"), "href": getattr(section, "href", "")})
            flatten_epub_toc(children, level + 1, result)
        else:
            result.append({"level": level, "title": getattr(item, "title", "Sección"), "href": getattr(item, "href", "")})
    return result


def inspect_epub(job: dict[str, Any], document: dict[str, Any], path: Path) -> None:
    book = epub.read_epub(str(path), options={"ignore_ncx": False})
    update_job(job["id"], stage="detecting_structure", progress=30, message="Leyendo navegación y spine del EPUB")
    entries = flatten_epub_toc(book.toc)
    source = "epub_nav"
    if not entries:
        source = "epub_spine"
        by_id = {item.id: item for item in book.get_items_of_type(ITEM_DOCUMENT)}
        for item_id, _linear in book.spine:
            item = by_id.get(item_id)
            if not item:
                continue
            soup = BeautifulSoup(item.get_content(), "html.parser")
            heading = soup.find(["h1", "h2", "h3"])
            entries.append({"level": 1, "title": heading.get_text(" ", strip=True) if heading else item.get_name(), "href": item.get_name()})
    persist_sections(document["id"], entries, source)
    metadata_title = book.get_metadata("DC", "title")
    metadata_author = book.get_metadata("DC", "creator")
    images = sum(1 for _ in book.get_items_of_type(ITEM_IMAGE))
    capabilities = {"sections": True, "pages": False, "locations": False, "visual_candidates": images}
    with db() as conn:
        conn.execute(
            "UPDATE source_documents SET title=%s,author=%s,parser_name='EbookLib',parser_version='0.19',status='ready',capabilities=%s,warnings=%s,updated_at=%s WHERE id=%s",
            ((metadata_title[0][0] if metadata_title else document["title"]), (metadata_author[0][0] if metadata_author else ""),
             Jsonb(capabilities), Jsonb(["EPUB refluible: se selecciona por capítulos, no por páginas físicas."]), datetime.now(timezone.utc), document["id"]),
        ); conn.commit()


def inspect(job: dict[str, Any]) -> None:
    with db() as conn:
        document = conn.execute("SELECT * FROM source_documents WHERE id=%s", (job["document_id"],)).fetchone()
        conn.execute("UPDATE source_documents SET status='inspecting' WHERE id=%s", (document["id"],)); conn.commit()
    path = local_copy(document["storage_key"], "." + document["format"])
    try:
        if document["format"] == "pdf": inspect_pdf(job, document, path)
        else: inspect_epub(job, document, path)
        finish(job["id"], "completed", "Documento listo para seleccionar")
    finally:
        path.unlink(missing_ok=True)


def section_rows(document_id):
    with db() as conn:
        return conn.execute("SELECT * FROM document_sections WHERE document_id=%s ORDER BY order_index", (document_id,)).fetchall()


def selected_page_groups(document: dict[str, Any], selection: dict[str, Any], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if selection["mode"] == "pages":
        pages = [page for item in selection["ranges"] for page in range(item["start"], item["end"] + 1)]
        label = ", ".join(f"{item['start']}-{item['end']}" for item in selection["ranges"])
        return [{"title": f"Páginas {label}", "pages": pages, "ranges": selection["ranges"], "heading_path": []}]
    children = defaultdict(list)
    by_id = {str(row["id"]): row for row in sections}
    for row in sections:
        if row["parent_id"]: children[str(row["parent_id"])].append(str(row["id"]))
    excluded = set(selection.get("excluded_section_ids") or [])
    def descendants(section_id):
        result = {section_id}
        for child in children.get(section_id, []): result |= descendants(child)
        return result
    excluded_expanded = set()
    for section_id in excluded:
        excluded_expanded |= descendants(section_id)
    if selection["mode"] == "sections":
        chosen = set(selection["section_ids"])
        def has_chosen_ancestor(section_id):
            parent = by_id[section_id]["parent_id"]
            while parent:
                if str(parent) in chosen: return True
                parent = by_id.get(str(parent), {}).get("parent_id")
            return False
        roots = [item for item in selection["section_ids"] if not has_chosen_ancestor(item)]
    else:
        roots = [str(row["id"]) for row in sections if not row["parent_id"]]
    groups = []
    for root_id in roots:
        row = by_id[root_id]
        included = descendants(root_id) - excluded_expanded if selection.get("include_descendants", True) else {root_id}
        relevant = [by_id[item] for item in included if item in by_id]
        start = min((item["page_start"] or 1) for item in relevant)
        end = max((item["page_end"] or start) for item in relevant)
        for part_start in range(start, end + 1, 20):
            part_end = min(part_start + 19, end)
            suffix = f" — Parte {(part_start-start)//20 + 1}" if end - start >= 20 else ""
            groups.append({"title": row["title"] + suffix, "pages": list(range(part_start, part_end + 1)),
                           "ranges": [{"start": part_start, "end": part_end}], "heading_path": [row["title"]]})
    if not groups:
        for start in range(1, (document["page_count"] or 0) + 1, 20):
            groups.append({"title": f"Páginas {start}-{min(start+19, document['page_count'])}",
                           "pages": list(range(start, min(start+19, document["page_count"]) + 1)),
                           "ranges": [{"start": start, "end": min(start+19, document["page_count"])}], "heading_path": []})
    return groups


def analyze_visual(data: bytes, media_type: str, model: str, context: str) -> tuple[str, float]:
    if not OPENROUTER_KEY or not model:
        return "", 0.0
    encoded = base64.b64encode(data).decode("ascii")
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=120,
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/JamesKristofUbiarco/Concat-notes", "X-Title": "Concat Notes"},
        json={"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Analiza únicamente este recorte documental. Describe datos, relaciones, ejes, leyendas y texto que no estén expresados en el contexto. No inventes información.\nContexto:\n" + context[:3000]},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
        ]}]})
    response.raise_for_status(); payload = response.json()
    return payload["choices"][0]["message"]["content"].strip(), float((payload.get("usage") or {}).get("cost") or 0.01)


def table_markdown(rows: list[list[Any]]) -> str:
    clean = [[" ".join(str(cell or "").split()).replace("|", "\\|") for cell in row] for row in rows]
    if not clean or not any(any(cell for cell in row) for row in clean): return ""
    width = max(len(row) for row in clean); clean = [row + [""] * (width - len(row)) for row in clean]
    return "\n".join(["| " + " | ".join(clean[0]) + " |", "| " + " | ".join(["---"] * width) + " |"] + ["| " + " | ".join(row) + " |" for row in clean[1:]])


def extract_pdf(job, document, run, path: Path) -> None:
    pdf = fitz.open(path); sections = section_rows(document["id"])
    groups = selected_page_groups(document, job["selection_json"], sections)
    selected_pages = sorted({page for group in groups for page in group["pages"]})
    page_markdown: dict[int, str] = {}; page_assets: dict[int, list[str]] = defaultdict(list)
    actual_cost = float(run["actual_cost_usd"] or 0); approved = float(run["approved_cost_usd"] or 0)
    model = ((run["model_snapshot"] or {}).get("api_model_id") or (run["model_snapshot"] or {}).get("effective_model") or "")
    element_order = 0
    seen_visuals: set[str] = set()
    budget_exhausted = False
    with db() as conn:
        conn.execute("DELETE FROM document_elements WHERE document_id=%s", (document["id"],)); conn.commit()
    for position, page_no in enumerate(selected_pages, 1):
        if cancelled(job["id"]): raise InterruptedError("Cancelado por el usuario")
        page = pdf[page_no - 1]
        text = page.get_text("text", sort=True).strip()
        if not text:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            text = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), lang="spa+eng").strip()
            if not text:
                text = "[Página sin texto legible después de OCR local.]"
        tables = []
        try:
            tables = [table_markdown(table.extract()) for table in page.find_tables().tables]
            tables = [table for table in tables if table]
        except Exception as exc:
            logger.debug("No se detectaron tablas estructuradas en página %s: %s", page_no, exc)
        if tables:
            text += "\n\n" + "\n\n".join(tables)
        page_markdown[page_no] = f"## Página {page_no}\n\n{text}"
        with db() as conn:
            conn.execute("INSERT INTO document_elements(id,document_id,order_index,page_number,element_type,text,content_hash,parser) VALUES(%s,%s,%s,%s,'paragraph',%s,%s,'PyMuPDF')",
                         (uuid.uuid4(), document["id"], element_order, page_no, text, hashlib.sha256(text.encode()).hexdigest())); conn.commit()
        element_order += 1
        for table in tables:
            with db() as conn:
                conn.execute("INSERT INTO document_elements(id,document_id,order_index,page_number,element_type,text,content_hash,parser) VALUES(%s,%s,%s,%s,'table',%s,%s,'PyMuPDF')",
                             (uuid.uuid4(), document["id"], element_order, page_no, table, hashlib.sha256(table.encode()).hexdigest())); conn.commit()
            element_order += 1
        for image_index, image_info in enumerate(page.get_images(full=True)):
            try:
                raw = pdf.extract_image(image_info[0]); image = Image.open(io.BytesIO(raw["image"])).convert("RGB")
                if image.width < 120 or image.height < 120: continue
                out = io.BytesIO(); image.save(out, format="WEBP", quality=82); data = out.getvalue()
                content_hash = hashlib.sha256(data).hexdigest(); key = f"documents/{document['id']}/assets/{content_hash}.webp"
                upload(key, data, "image/webp")
                description = ""
                informative = image.width * image.height >= (20_000 if job["profile"] == "accurate" else 80_000)
                if job["profile"] != "local" and informative and content_hash not in seen_visuals and actual_cost + 0.025 <= approved:
                    description, cost = analyze_visual(data, "image/webp", model, text[:1500]); actual_cost += cost
                elif job["profile"] != "local" and informative and actual_cost + 0.025 > approved:
                    budget_exhausted = True
                seen_visuals.add(content_hash)
                asset_id = uuid.uuid4(); page_assets[page_no].append(str(asset_id))
                with db() as conn:
                    conn.execute("INSERT INTO document_assets(id,document_id,storage_key,media_type,kind,page_number,content_hash,width,height,description,analysis_model) VALUES(%s,%s,%s,'image/webp','figure',%s,%s,%s,%s,%s,%s) ON CONFLICT(storage_key) DO NOTHING",
                                 (asset_id, document["id"], key, page_no, content_hash, image.width, image.height, description, model));
                    existing = conn.execute("SELECT id FROM document_assets WHERE storage_key=%s", (key,)).fetchone(); asset_id = existing["id"]
                    conn.execute("INSERT INTO document_elements(id,document_id,order_index,page_number,element_type,caption,visual_description,asset_id,content_hash,parser,model,status) VALUES(%s,%s,%s,%s,'figure',%s,%s,%s,%s,'PyMuPDF',%s,%s)",
                                 (uuid.uuid4(), document["id"], element_order, page_no, f"Figura de la página {page_no}", description, asset_id, content_hash, model, "enriched" if description else "retained")); conn.commit()
                page_assets[page_no][-1] = str(asset_id); element_order += 1
                page_markdown[page_no] += f"\n\n![Figura de la página {page_no}]({public_url(key)})"
                if description: page_markdown[page_no] += f"\n\n> **Contenido visual:** {description}"
            except Exception as exc:
                logger.warning("No se pudo extraer una figura p%s/%s: %s", page_no, image_index, exc)
        update_job(job["id"], stage="extracting", progress=10 + round(position / max(1, len(selected_pages)) * 75), message=f"Extrayendo página {position} de {len(selected_pages)}")
    with db() as conn:
        conn.execute("DELETE FROM document_drafts WHERE run_id=%s AND raw_note_id IS NULL", (run["id"],))
        for index, group in enumerate(groups):
            markdown = f"# {group['title']}\n\n" + "\n\n".join(page_markdown[p] for p in group["pages"] if p in page_markdown)
            asset_ids = [asset for p in group["pages"] for asset in page_assets[p]]
            conn.execute("INSERT INTO document_drafts(id,run_id,order_index,title,heading_path,page_ranges,source_markdown,course_name,course_module,class_title,asset_ids) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                         (uuid.uuid4(), run["id"], index, group["title"], Jsonb(group["heading_path"]), Jsonb(group["ranges"]), markdown,
                          document["title"], document["title"], group["title"][:255], Jsonb(asset_ids)))
        warnings = ["Se alcanzó el presupuesto visual; la extracción local se conservó completa."] if budget_exhausted else []
        conn.execute("UPDATE document_runs SET status='ready',actual_cost_usd=%s,warnings=%s,finished_at=%s WHERE id=%s", (actual_cost, Jsonb(warnings), datetime.now(timezone.utc), run["id"])); conn.commit()


def extract_epub(job, document, run, path: Path) -> None:
    book = epub.read_epub(str(path)); sections = section_rows(document["id"])
    actual_cost = float(run["actual_cost_usd"] or 0); approved = float(run["approved_cost_usd"] or 0)
    model = ((run["model_snapshot"] or {}).get("api_model_id") or (run["model_snapshot"] or {}).get("effective_model") or "")
    seen_visuals: set[str] = set()
    budget_exhausted = False
    element_order = 0
    with db() as conn:
        conn.execute("DELETE FROM document_elements WHERE document_id=%s", (document["id"],)); conn.commit()
    selected = set(job["selection_json"].get("section_ids") or [])
    excluded = set(job["selection_json"].get("excluded_section_ids") or [])
    if selected and job["selection_json"].get("include_descendants", True):
        children = defaultdict(list)
        for row in sections:
            if row["parent_id"]: children[str(row["parent_id"])].append(str(row["id"]))
        pending = list(selected)
        while pending:
            child_ids = children.get(pending.pop(), [])
            selected.update(child_ids); pending.extend(child_ids)
        pending = list(excluded)
        while pending:
            child_ids = children.get(pending.pop(), [])
            excluded.update(child_ids); pending.extend(child_ids)
    section_by_href = {str(row["epub_href"]).split("#")[0]: row for row in sections if row["epub_href"]}
    docs = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        href = item.get_name()
        if href.lower().endswith(("nav.xhtml", "toc.ncx")) or "nav" in (item.get_properties() or []):
            continue
        section = section_by_href.get(href)
        if job["selection_json"]["mode"] == "sections" and (not section or str(section["id"]) not in selected or str(section["id"]) in excluded):
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "iframe", "style"]): tag.decompose()
        heading = soup.find(["h1", "h2", "h3"])
        title = heading.get_text(" ", strip=True) if heading else (section["title"] if section else href)
        parts = [f"# {title}"]
        asset_ids = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "table", "img"]):
            if tag.name == "img":
                src = tag.get("src", ""); resolved = posixpath.normpath(posixpath.join(posixpath.dirname(href), src))
                image_item = book.get_item_with_href(resolved)
                if not image_item: continue
                try:
                    image = Image.open(io.BytesIO(image_item.get_content())).convert("RGB")
                    if image.width < 120 or image.height < 120: continue
                    out = io.BytesIO(); image.save(out, "WEBP", quality=82); data = out.getvalue(); digest = hashlib.sha256(data).hexdigest()
                    key = f"documents/{document['id']}/assets/{digest}.webp"; upload(key, data, "image/webp"); asset_id = uuid.uuid4()
                    description = ""
                    informative = image.width * image.height >= (20_000 if job["profile"] == "accurate" else 80_000)
                    if job["profile"] != "local" and informative and digest not in seen_visuals and actual_cost + 0.025 <= approved:
                        description, cost = analyze_visual(data, "image/webp", model, title); actual_cost += cost
                    elif job["profile"] != "local" and informative and actual_cost + 0.025 > approved:
                        budget_exhausted = True
                    seen_visuals.add(digest)
                    with db() as conn:
                        conn.execute("INSERT INTO document_assets(id,document_id,storage_key,media_type,kind,content_hash,width,height,description,analysis_model) VALUES(%s,%s,%s,'image/webp','figure',%s,%s,%s,%s,%s) ON CONFLICT(storage_key) DO NOTHING",
                                     (asset_id, document["id"], key, digest, image.width, image.height, description, model)); existing = conn.execute("SELECT id FROM document_assets WHERE storage_key=%s", (key,)).fetchone(); conn.commit()
                    asset_ids.append(str(existing["id"])); parts.append(f"![{tag.get('alt') or 'Figura'}]({public_url(key)})")
                    if description: parts.append(f"> **Contenido visual:** {description}")
                    with db() as conn:
                        conn.execute("INSERT INTO document_elements(id,document_id,section_id,order_index,element_type,caption,visual_description,asset_id,content_hash,parser,model,status) VALUES(%s,%s,%s,%s,'figure',%s,%s,%s,%s,'EbookLib',%s,%s)",
                                     (uuid.uuid4(), document["id"], section["id"] if section else None, element_order, tag.get("alt") or "Figura", description, existing["id"], digest, model, "enriched" if description else "retained")); conn.commit()
                    element_order += 1
                except Exception: continue
            else:
                text = tag.get_text(" ", strip=True)
                if not text: continue
                if tag.name.startswith("h") and text == title and len(parts) == 1: continue
                prefix = "#" * min(6, int(tag.name[1])) + " " if tag.name.startswith("h") else "- " if tag.name == "li" else ""
                parts.append(prefix + text)
                element_type = "heading" if tag.name.startswith("h") else "list" if tag.name == "li" else "table" if tag.name == "table" else "paragraph"
                with db() as conn:
                    conn.execute("INSERT INTO document_elements(id,document_id,section_id,order_index,element_type,text,content_hash,parser) VALUES(%s,%s,%s,%s,%s,%s,%s,'EbookLib')",
                                 (uuid.uuid4(), document["id"], section["id"] if section else None, element_order, element_type, text, hashlib.sha256(text.encode()).hexdigest())); conn.commit()
                element_order += 1
        docs.append((title, "\n\n".join(parts), asset_ids, section))
    with db() as conn:
        conn.execute("DELETE FROM document_drafts WHERE run_id=%s AND raw_note_id IS NULL", (run["id"],))
        for index, (title, markdown, assets, section) in enumerate(docs):
            conn.execute("INSERT INTO document_drafts(id,run_id,order_index,title,heading_path,page_ranges,source_markdown,course_name,course_module,class_title,asset_ids) VALUES(%s,%s,%s,%s,%s,'[]',%s,%s,%s,%s,%s)",
                         (uuid.uuid4(), run["id"], index, title, Jsonb([title]), markdown, document["title"], document["title"], title[:255], Jsonb(assets)))
        warnings = ["Se alcanzó el presupuesto visual; la extracción local se conservó completa."] if budget_exhausted else []
        conn.execute("UPDATE document_runs SET status='ready',actual_cost_usd=%s,warnings=%s,finished_at=%s WHERE id=%s", (actual_cost, Jsonb(warnings), datetime.now(timezone.utc), run["id"])); conn.commit()


def process(job: dict[str, Any]) -> None:
    with db() as conn:
        document = conn.execute("SELECT * FROM source_documents WHERE id=%s", (job["document_id"],)).fetchone()
        run = conn.execute("SELECT * FROM document_runs WHERE id=%s", ((job["options_json"] or {})["run_id"],)).fetchone()
    path = local_copy(document["storage_key"], "." + document["format"])
    try:
        update_job(job["id"], stage="extracting", progress=5, message="Preparando selección estructurada")
        if document["format"] == "pdf": extract_pdf(job, document, run, path)
        else: extract_epub(job, document, run, path)
        finish(job["id"], "completed", "Extracción lista para previsualizar")
    finally:
        path.unlink(missing_ok=True)


def recover_stale_jobs() -> None:
    with db() as conn:
        conn.execute("UPDATE document_jobs SET status='pending',stage='queued',message='Recuperado tras reinicio' WHERE status='running' AND (heartbeat_at IS NULL OR heartbeat_at < NOW() - INTERVAL '90 seconds')")
        conn.commit()


def main() -> None:
    recover_stale_jobs(); logger.info("Worker documental iniciado")
    while True:
        job = claim_job()
        if not job:
            time.sleep(POLL_SECONDS); continue
        try:
            if job["kind"] == "inspect": inspect(job)
            elif job["kind"] == "process": process(job)
            else: raise ValueError(f"Tipo de job desconocido: {job['kind']}")
        except InterruptedError as exc:
            finish(job["id"], "cancelled", str(exc))
        except Exception as exc:
            logger.exception("Falló job %s", job["id"])
            finish(job["id"], "failed", "El trabajo documental falló", str(exc))
            with db() as conn:
                if job["kind"] == "inspect": conn.execute("UPDATE source_documents SET status='failed',error=%s WHERE id=%s", (str(exc), job["document_id"]))
                else:
                    run_id = (job["options_json"] or {}).get("run_id")
                    if run_id: conn.execute("UPDATE document_runs SET status='failed',warnings=%s WHERE id=%s", (Jsonb([str(exc)]), run_id))
                conn.commit()


if __name__ == "__main__": main()
