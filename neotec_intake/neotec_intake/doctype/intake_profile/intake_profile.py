import frappe
from frappe.model.document import Document


class IntakeProfile(Document):
    def validate(self):
        if self.options:
            try:
                frappe.parse_json(self.options)
            except Exception:
                frappe.throw("Options must be valid JSON.")
