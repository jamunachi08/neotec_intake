app_name = "neotec_intake"
app_title = "Neotec DocIntake"
app_publisher = "Neotec Integrated Solution"
app_description = "Read images, PDFs, Excel/CSV and turn them into draft ERPNext documents."
app_email = "support@neotec.ai"
app_license = "MIT"

doctype_js = {"Intake Document": "public/js/intake_document.js"}

app_include_js = []

after_install = "neotec_intake.install.after_install"
