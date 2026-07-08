"""Pluggable LLM client for unstructured extraction (PDF text, images).

Local Ollama is the default so documents never leave the site (PDPL / data
sovereignty). An OpenAI-compatible endpoint is also supported. Structured files
(Excel/CSV) never touch this module.
"""
import json
import frappe
import requests


def _settings():
    try:
        s = frappe.get_single("Intake Settings")
    except Exception:
        return None
    return s


def available() -> bool:
    s = _settings()
    return bool(s and (s.provider or "none") != "none")


def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    # tolerate code fences / prose around the JSON
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [-1])
    if start > 0:
        text = text[start:]
    try:
        return json.loads(text)
    except Exception:
        try:
            return frappe.parse_json(text)
        except Exception:
            return None


def chat_json(prompt: str, images_b64: list[str] | None = None) -> dict | None:
    """Return parsed JSON from the configured model, or None."""
    s = _settings()
    if not s or (s.provider or "none") == "none":
        return None
    provider = s.provider
    base = (s.base_url or "").rstrip("/")
    is_vision = bool(images_b64)
    model = (s.vision_model if is_vision else s.model) or s.model
    timeout = 120
    try:
        if provider == "ollama":
            msg = {"role": "user", "content": prompt}
            if images_b64:
                msg["images"] = images_b64
            r = requests.post(f"{base}/api/chat", json={
                "model": model, "messages": [msg], "stream": False, "format": "json",
                "options": {"temperature": 0},
            }, timeout=timeout)
            r.raise_for_status()
            return _extract_json(r.json().get("message", {}).get("content", ""))
        else:  # openai_compatible
            content = [{"type": "text", "text": prompt}]
            for b in (images_b64 or []):
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b}"}})
            headers = {"Content-Type": "application/json"}
            key = s.get_password("api_key") if s.get("api_key") else None
            if key:
                headers["Authorization"] = f"Bearer {key}"
            r = requests.post(f"{base}/v1/chat/completions", headers=headers, json={
                "model": model,
                "messages": [{"role": "user", "content": content if images_b64 else prompt}],
                "temperature": 0, "response_format": {"type": "json_object"},
            }, timeout=timeout)
            r.raise_for_status()
            return _extract_json(r.json()["choices"][0]["message"]["content"])
    except requests.exceptions.ConnectionError:
        # expected when no model is reachable — fall back silently to heuristics
        return None
    except Exception as e:
        frappe.logger("neotec_intake").warning(f"LLM extract failed: {e}")
        return None


def schema_hint(target_doctype: str, child_table_field: str | None = None) -> str:
    """A compact description of the target fields, to steer the model."""
    try:
        meta = frappe.get_meta(target_doctype)
        head = [f.fieldname for f in meta.fields
                if f.fieldtype in ("Data", "Date", "Datetime", "Currency", "Float",
                                   "Int", "Select", "Link", "Small Text", "Text")
                and not f.hidden][:25]
        hint = f"Header fields: {', '.join(head)}."
        if child_table_field:
            try:
                ctype = meta.get_field(child_table_field).options
                cmeta = frappe.get_meta(ctype)
                cols = [f.fieldname for f in cmeta.fields
                        if f.fieldtype in ("Data", "Date", "Currency", "Float", "Int",
                                           "Select", "Link", "Small Text") and not f.hidden][:20]
                hint += f" Line-item fields ({child_table_field}): {', '.join(cols)}."
            except Exception:
                pass
        return hint
    except Exception:
        return ""
