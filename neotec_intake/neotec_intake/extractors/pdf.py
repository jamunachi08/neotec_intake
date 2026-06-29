"""PDF extraction: pull text deterministically, then (optionally) let the model
structure it into header fields and line items."""
import io
from . import llm, invoice_text


def _text(content: bytes, max_pages: int = 10) -> str:
    # try pdfplumber, then pdfminer, then pypdf (bundled with Frappe v15), then PyPDF2
    try:
        import pdfplumber
        out = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for pg in pdf.pages[:max_pages]:
                out.append(pg.extract_text() or "")
        if any(o.strip() for o in out):
            return "\n".join(out)
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text
        txt = extract_text(io.BytesIO(content), maxpages=max_pages) or ""
        if txt.strip():
            return txt
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(content))
        txt = "\n".join((p.extract_text() or "") for p in rd.pages[:max_pages])
        if txt.strip():
            return txt
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        rd = PdfReader(io.BytesIO(content))
        return "\n".join((p.extract_text() or "") for p in rd.pages[:max_pages])
    except Exception:
        return ""


def extract(content: bytes, target_doctype: str, child_table_field: str = "",
            max_pages: int = 10, company_vat: str | None = None) -> dict:
    text = _text(content, max_pages)
    payload = {"fields": {}, "rows": [], "raw_text": text}
    if not text.strip():
        payload["message"] = "No selectable text in PDF. If it is a scan, use an image source or enable OCR."
        return payload
    if llm.available():
        hint = llm.schema_hint(target_doctype, child_table_field)
        prompt = (
            f"Extract structured data from this document for an ERPNext '{target_doctype}'.\n"
            f"{hint}\n"
            "Return ONLY JSON: {\"fields\": {header fieldname: value}, "
            "\"rows\": [{line fieldname: value}, ...]}. Use ISO dates (YYYY-MM-DD) and plain numbers.\n\n"
            f"DOCUMENT:\n{text[:12000]}"
        )
        js = llm.chat_json(prompt)
        if isinstance(js, dict) and (js.get("fields") or js.get("rows")):
            payload["fields"] = js.get("fields", {}) or {}
            payload["rows"] = js.get("rows", []) or []
            return payload
    # deterministic fallback for bilingual / ZATCA tax invoices (no AI needed)
    if invoice_text.looks_like_invoice(text):
        h = invoice_text.parse(text, company_vat=company_vat)
        if h["fields"] or h["rows"]:
            payload["fields"], payload["rows"] = h["fields"], h["rows"]
            payload["message"] = "Parsed with the built-in invoice reader (no AI). Review the values before creating the document."
            return payload
    payload["message"] = ("Text extracted but not auto-structured. Configure an AI model in "
                          "Intake Settings, or map fields from the raw text.")
    return payload
