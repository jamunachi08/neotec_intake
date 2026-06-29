"""Whitelisted entry points the Intake Document form calls."""
import json
import frappe
from neotec_intake.neotec_intake.extractors import base
from neotec_intake.neotec_intake.builders import mapping, core


@frappe.whitelist()
def extract(docname):
    doc = frappe.get_doc("Intake Document", docname)
    if not doc.attachment:
        frappe.throw("Attach a file first.")
    profile = frappe.get_doc("Intake Profile", doc.intake_profile)
    if not profile.enabled:
        frappe.throw("This Intake Profile is disabled.")
    payload = base.run(doc.attachment, profile)
    mapped = mapping.apply_mapping(payload, profile)
    out = {"header": mapped.get("header") or {}, "rows": mapped.get("rows") or []}
    raw = payload.get("raw_text") or ""
    if not out["header"] and not out["rows"] and raw:
        out["raw_text"] = raw[:8000]
    doc.extracted_json = json.dumps(out, indent=2, default=str)
    doc.source_type_detected = payload.get("source_type")
    msg = payload.get("message") or ""
    if out["header"] or out["rows"]:
        doc.status = "Extracted"
        doc.log = msg or f"Extracted {len(out['rows'])} row(s). Review, then Create Document."
    elif raw:
        doc.status = "Extracted"
        doc.log = (msg or "") + " Text was read but not auto-structured — configure an AI model in Intake Settings (see raw_text below), or map fields manually."
    else:
        doc.status = "Extracted" if msg else "Error"
        doc.log = msg or "Nothing extracted — check the file and the profile's Field Map."
    doc.save()
    return {"status": doc.status, "mapped": out, "message": doc.log}


@frappe.whitelist()
def commit(docname):
    doc = frappe.get_doc("Intake Document", docname)
    if doc.status == "Committed" and doc.created_document:
        frappe.throw(f"Already created {doc.created_doctype} {doc.created_document}.")
    profile = frappe.get_doc("Intake Profile", doc.intake_profile)
    try:
        mapped = frappe.parse_json(doc.extracted_json) if doc.extracted_json else {"header": {}, "rows": []}
    except Exception:
        frappe.throw("Extracted JSON is not valid. Fix it and retry.")
    extra = {}
    for f in ("supplier", "item_code", "expense_account", "cost_center"):
        if doc.get(f):
            extra[f] = doc.get(f)
    created = core.build(profile, mapped, extra)
    if created:
        doc.created_doctype = created[0]["doctype"]
        doc.created_document = created[0]["name"]
        doc.status = "Committed"
        doc.log = "Created (draft): " + ", ".join(f"{c['doctype']} {c['name']}" for c in created)
    doc.save()
    return {"created": created, "log": doc.log}
