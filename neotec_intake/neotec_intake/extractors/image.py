"""Image extraction via a vision model (data stays local with Ollama). Optional
local OCR (pytesseract) can run first when enabled."""
import base64
import io
from . import llm, invoice_text


def _ocr(content: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(content))) or ""
    except Exception:
        return ""


def extract(content: bytes, target_doctype: str, child_table_field: str = "",
            ocr_enabled: bool = False, company_vat: str | None = None) -> dict:
    payload = {"fields": {}, "rows": [], "raw_text": ""}
    if ocr_enabled:
        payload["raw_text"] = _ocr(content)
    if not llm.available():
        if payload["raw_text"] and invoice_text.looks_like_invoice(payload["raw_text"]):
            h = invoice_text.parse(payload["raw_text"], company_vat=company_vat)
            if h["fields"] or h["rows"]:
                payload["fields"], payload["rows"] = h["fields"], h["rows"]
                payload["message"] = "Parsed OCR text with the built-in invoice reader (no AI). Review before creating."
                return payload
        payload["message"] = ("Configure a vision model in Intake Settings to read images "
                              "(e.g. local Ollama llama3.2-vision), or enable OCR for invoice text.")
        return payload
    hint = llm.schema_hint(target_doctype, child_table_field)
    b64 = base64.b64encode(content).decode()
    prompt = (
        f"Read this document image and extract data for an ERPNext '{target_doctype}'.\n"
        f"{hint}\n"
        "Return ONLY JSON: {\"fields\": {header fieldname: value}, "
        "\"rows\": [{line fieldname: value}, ...]}. ISO dates, plain numbers."
    )
    if payload["raw_text"]:
        prompt += f"\n\nOCR text (reference):\n{payload['raw_text'][:6000]}"
    js = llm.chat_json(prompt, images_b64=[b64])
    if isinstance(js, dict):
        payload["fields"] = js.get("fields", {}) or {}
        payload["rows"] = js.get("rows", []) or []
    else:
        payload["message"] = "The vision model returned nothing usable. Check Intake Settings / model."
    return payload
