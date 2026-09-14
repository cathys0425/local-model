"""Bounded local document ingestion; no URL fetching or cloud OCR."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from email import policy
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 5


class InputError(ValueError):
    pass


def poppler_tool(name):
    override = os.environ.get("POPPLER_BIN")
    found = str(Path(override) / name) if override else shutil.which(name)
    if not found:
        raise InputError(f"{name} is required for scanned PDFs; set POPPLER_BIN to your Poppler bin folder")
    return found


def ocr_image(path):
    binary = ROOT / ".bin" / "local-ocr"
    if not binary.is_file():
        raise InputError("Local OCR helper missing. Run the clang setup command in part2/MULTIFORMAT.md")
    result = subprocess.run([str(binary), str(path)], capture_output=True, text=True, timeout=45, check=True)
    boxes = json.loads(result.stdout)
    if not boxes:
        raise InputError("OCR found no text")
    # Cluster by the vertical centers and order left-to-right within each row.
    rows = []
    for box in sorted(boxes, key=lambda b: -b["y"]):
        row = next((r for r in rows if abs(r[0]["y"] - box["y"]) < min(r[0]["height"], box["height"]) * .55), None)
        if row is None:
            rows.append([box])
        else:
            row.append(box)
    text = "\n".join("  ".join(b["text"] for b in sorted(r, key=lambda b: b["x"])) for r in rows)
    minimum = min(b["confidence"] for b in boxes)
    return text, {"method": "apple_vision", "minimum_confidence": minimum,
                  "boxes": boxes, "review_required": minimum < .8}


def read_document(path):
    """Read a single invoice/body. Email attachments are handled by load_inputs."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise InputError("Document exceeds the 10 MiB demo limit")
    raw = path.read_bytes()
    info = {"file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
            "format": path.suffix.lower().lstrip("."), "pages": []}
    if path.suffix.lower() == ".txt":
        text = raw.decode("utf-8")
        info["pages"] = [{"method": "utf8"}]
    elif path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        text, page = ocr_image(path)
        info["pages"] = [page]
    elif path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
            raise InputError("Encrypted, empty, or more than five-page PDF is outside the demo contract")
        texts = []
        for index, page in enumerate(reader.pages):
            native = page.extract_text(extraction_mode="layout") or ""
            if page.images or not native.strip():
                if float(page.mediabox.width) > 1500 or float(page.mediabox.height) > 1500:
                    raise InputError("PDF page dimensions exceed the demo rasterization limit")
                with tempfile.TemporaryDirectory() as folder:
                    prefix = str(Path(folder) / "page")
                    subprocess.run([poppler_tool("pdftoppm"), "-f", str(index + 1), "-l", str(index + 1),
                                    "-scale-to", "2400", "-singlefile", "-png", str(path), prefix],
                                   check=True, capture_output=True, timeout=45)
                    extracted, detail = ocr_image(prefix + ".png")
                # Mixed native/image content needs visual review: neither layer
                # alone establishes the complete, authentic invoice content.
                detail["review_required"] = detail["review_required"] or bool(native.strip())
                if native.strip():
                    detail["native_text"] = native
                    detail["warning"] = "Mixed image/text PDF requires source review"
            else:
                extracted, detail = native, {"method": "pdf_text"}
            texts.append(extracted)
            info["pages"].append(dict(detail, page=index + 1))
        text = "\n\n".join(texts)
    else:
        raise InputError(f"Unsupported document extension: {path.suffix}")
    if not text.strip() or len(text) > 24000:
        raise InputError("Converted document is empty or exceeds 24,000 characters")
    # Keep the exact converted text used for source checks in the audit record.
    info["text"] = text
    return text, info


def read_email(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise InputError("Email exceeds the 10 MiB demo limit")
    raw = path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw)
    body = message.get_body(preferencelist=("plain",))
    if body is None:
        raise InputError("Email needs a text/plain body; HTML-only email is not supported")
    attachments = list(message.iter_attachments())
    info = {"file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
            "format": "eml", "method": "mime_plaintext", "subject": str(message.get("Subject", "")),
            "attachment_count": len(attachments)}
    # Subject is source content too; inspect it for conflicts/instructions.
    text = info["subject"] + "\n" + body.get_content()
    if len(text) > 24000:
        raise InputError("Email body exceeds 24,000 characters")
    info["text"] = text
    return text, attachments, info


def load_inputs(invoice_path, email_path=None):
    start = time.monotonic()
    sources, email_text = [], ""
    if Path(invoice_path).suffix.lower() == ".eml":
        body, attachments, source = read_email(invoice_path)
        sources.append(source)
        if attachments:
            if len(attachments) != 1:
                raise InputError("Select one invoice explicitly; multiple email attachments are ambiguous")
            attachment = attachments[0]
            suffix = Path(attachment.get_filename() or "").suffix.lower()
            # Never use untrusted attachment paths on disk.
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / ("invoice" + suffix)
                target.write_bytes(attachment.get_payload(decode=True) or b"")
                invoice_text, detail = read_document(target)
            detail["file"] = f"{Path(invoice_path).resolve()}#attachment"
            detail["attachment_name"] = attachment.get_filename()
            sources.append(detail)
            email_text = body
        else:
            invoice_text = body
    else:
        invoice_text, source = read_document(invoice_path)
        sources.append(source)
    if email_path:
        if Path(email_path).suffix.lower() == ".eml":
            text, attachments, source = read_email(email_path)
            if attachments:
                raise InputError("Companion email has attachments; pass the .eml as --invoice or remove ambiguity")
        else:
            text, source = read_document(email_path)
        email_text += "\n" + text
        sources.append(source)
    review = any(page.get("review_required") for source in sources for page in source.get("pages", []))
    return invoice_text, email_text, {"sources": sources, "review_required": review,
                                    "latency_seconds": round(time.monotonic() - start, 3)}


def resolve_files(invoice_path, email_path=None, **kwargs):
    from agent import resolve_invoice
    try:
        invoice, email, ingestion = load_inputs(invoice_path, email_path)
    except Exception as exc:
        return resolve_invoice("", input_error=f"Document ingestion failed: {type(exc).__name__}: {exc}", **kwargs)
    return resolve_invoice(invoice, email_text=email, ingestion=ingestion, **kwargs)
