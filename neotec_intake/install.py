import frappe


def after_install():
    _ensure_settings()
    _ensure_profiles()
    frappe.db.commit()


def _ensure_settings():
    try:
        s = frappe.get_single("Intake Settings")
        if not s.get("provider"):
            s.provider = "none"
            s.base_url = "http://localhost:11434"
            s.model = "llama3.1"
            s.vision_model = "llama3.2-vision"
            s.save(ignore_permissions=True)
    except Exception:
        pass


_SAMPLES = [
    {"profile_name": "Supplier Invoice (Excel)", "target_doctype": "Purchase Invoice",
     "builder": "purchase_invoice", "source_type": "excel", "child_table_field": "items",
     "fields": [("Supplier", "supplier", "header", "strip"), ("Date", "posting_date", "header", "date"),
                ("Description", "description", "row", "none"), ("Qty", "qty", "row", "number"),
                ("Rate", "rate", "row", "number")]},
    {"profile_name": "Leads (CSV)", "target_doctype": "Lead", "builder": "lead", "source_type": "csv",
     "fields": [("Name", "lead_name", "row", "strip"), ("Email", "email_id", "row", "strip"),
                ("Mobile", "mobile_no", "row", "strip"), ("Company", "company_name", "row", "strip")]},
    {"profile_name": "Journal (Excel)", "target_doctype": "Journal Entry", "builder": "journal_entry",
     "source_type": "excel", "child_table_field": "accounts",
     "fields": [("Date", "posting_date", "header", "date"), ("Account", "account", "row", "strip"),
                ("Debit", "debit", "row", "number"), ("Credit", "credit", "row", "number")]},
    {"profile_name": "Invoice/Receipt (Image or PDF → AI)", "target_doctype": "Purchase Invoice",
     "builder": "purchase_invoice", "source_type": "auto", "child_table_field": "items", "fields": []},
]


def _ensure_profiles():
    for s in _SAMPLES:
        if frappe.db.exists("Intake Profile", s["profile_name"]):
            continue
        doc = frappe.new_doc("Intake Profile")
        doc.profile_name = s["profile_name"]
        doc.target_doctype = s["target_doctype"]
        doc.builder = s["builder"]
        doc.source_type = s["source_type"]
        doc.child_table_field = s.get("child_table_field")
        for src, tgt, scope, tr in s["fields"]:
            doc.append("field_map", {"source_key": src, "target_field": tgt, "scope": scope, "transform": tr})
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.clear_messages()
