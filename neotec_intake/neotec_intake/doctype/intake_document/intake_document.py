import frappe
from frappe.model.document import Document


class IntakeDocument(Document):
    def before_save(self):
        if not self.title and self.intake_profile:
            self.title = f"{self.intake_profile} · {frappe.utils.nowdate()}"
