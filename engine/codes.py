"""Short plain-language labels for common codes (display only; codes are what the engine uses).

Descriptions are abbreviated paraphrases for a demo, not official code-set text.
"""
HCPCS = {
    "99211": "Office visit, established patient (minimal)", "99212": "Office visit, established (level 2)",
    "99213": "Office visit, established (level 3)", "99214": "Office visit, established (level 4)",
    "99215": "Office visit, established (level 5, highest)", "99201": "Office visit, new patient (level 1)",
    "99202": "Office visit, new patient (level 2)", "99203": "Office visit, new patient (level 3)",
    "99204": "Office visit, new patient (level 4)", "99205": "Office visit, new patient (level 5, highest)",
    "99221": "Initial hospital care (level 1)", "99222": "Initial hospital care (level 2)",
    "99223": "Initial hospital care (level 3, highest)", "99231": "Subsequent hospital care (level 1)",
    "99232": "Subsequent hospital care (level 2)", "99233": "Subsequent hospital care (level 3, highest)",
    "99281": "Emergency visit (level 1)", "99282": "Emergency visit (level 2)", "99283": "Emergency visit (level 3)",
    "99284": "Emergency visit (level 4)", "99285": "Emergency visit (level 5, highest)",
    "36415": "Routine blood draw", "85025": "Complete blood count", "80053": "Comprehensive metabolic panel",
    "80048": "Basic metabolic panel", "85610": "Prothrombin time (clotting)", "80061": "Lipid panel",
    "84443": "Thyroid stimulating hormone", "83036": "Hemoglobin A1c", "82306": "Vitamin D level",
    "81001": "Urinalysis", "84153": "PSA test", "82728": "Ferritin", "83540": "Iron level",
    "82607": "Vitamin B-12 level", "84439": "Free thyroxine (T4)", "86803": "Hepatitis C antibody",
    "87086": "Urine culture", "88305": "Surgical pathology, level IV",
    "97110": "Therapeutic exercise", "97140": "Manual therapy", "98941": "Chiropractic manipulation, 3-4 regions",
    "93000": "ECG with interpretation", "93010": "ECG interpretation only", "71010": "Chest X-ray, 1 view",
    "71020": "Chest X-ray, 2 views", "A0425": "Ground ambulance mileage", "G0008": "Flu shot administration",
    "90658": "Flu vaccine", "70553": "MRI brain without & with contrast", "70551": "MRI brain without contrast",
    "72148": "MRI lumbar spine without contrast", "72141": "MRI cervical spine without contrast",
    "73721": "MRI leg joint without contrast", "71250": "CT chest without contrast",
    "71260": "CT chest with contrast", "70450": "CT head without contrast", "74150": "CT abdomen without contrast",
    "78452": "Nuclear heart perfusion study", "93307": "Echocardiogram", "93880": "Carotid artery ultrasound",
    "77080": "Bone density scan (DXA)", "76700": "Abdominal ultrasound", "27447": "Total knee replacement",
    "27130": "Total hip replacement", "66984": "Cataract surgery with lens implant",
    "45378": "Diagnostic colonoscopy", "45380": "Colonoscopy with biopsy", "43239": "Upper GI endoscopy with biopsy",
    "29881": "Knee arthroscopy with meniscectomy", "63047": "Lumbar laminectomy", "33533": "Coronary bypass (arterial)",
    "92980": "Coronary stent placement", "93510": "Left heart catheterization", "J1885": "Ketorolac injection",
    "J9310": "Rituximab infusion (100 mg)", "J0881": "Darbepoetin injection", "E0601": "CPAP device",
    "E1390": "Oxygen concentrator", "K0001": "Standard wheelchair",
}

DRG = {
    "470": "Major joint replacement, lower extremity w/o MCC", "291": "Heart failure & shock w/ MCC",
    "292": "Heart failure & shock w/ CC", "293": "Heart failure & shock w/o CC/MCC",
    "871": "Septicemia w/ MCC", "190": "COPD w/ MCC", "191": "COPD w/ CC", "194": "Simple pneumonia w/ CC",
    "193": "Simple pneumonia w/ MCC", "392": "GI disorders w/o MCC", "690": "Kidney & urinary infection w/o MCC",
    "247": "Coronary stent (drug-eluting) w/o MCC", "460": "Spinal fusion (non-cervical) w/o MCC",
    "885": "Psychoses", "312": "Syncope & collapse", "313": "Chest pain", "65": "Stroke w/ CC",
    "378": "GI hemorrhage w/ CC", "683": "Renal failure w/ CC", "603": "Cellulitis w/o MCC",
    "641": "Nutritional & metabolic disorders w/o MCC", "481": "Hip & femur procedures w/ CC",
    "236": "Coronary bypass w/o MCC", "246": "Coronary stent (drug-eluting) w/ MCC",
}

ICD9 = {
    "4019": "Hypertension", "25000": "Type 2 diabetes", "2724": "High cholesterol", "2720": "Pure hypercholesterolemia",
    "4280": "Congestive heart failure", "41401": "Coronary artery disease", "42731": "Atrial fibrillation",
    "496": "COPD", "5990": "Urinary tract infection", "486": "Pneumonia", "7862": "Cough", "V5869": "Long-term medication use",
    "2449": "Hypothyroidism", "2859": "Anemia", "7140": "Rheumatoid arthritis", "71590": "Osteoarthritis",
    "311": "Depression", "5856": "End-stage renal disease", "5859": "Chronic kidney disease", "78650": "Chest pain",
    "7242": "Low back pain", "V7231": "Routine gynecological exam", "36616": "Cataract", "78079": "Malaise and fatigue",
    "V5861": "Long-term anticoagulant use", "4011": "Benign hypertension", "2768": "Hypokalemia", "4241": "Aortic valve disorder",
    "V4501": "Cardiac pacemaker", "7802": "Syncope", "78820": "Urinary retention", "3310": "Alzheimer's disease",
}

CHRONIC_LABELS = {
    "sp_alzhdmta": "Alzheimer's / dementia", "sp_chf": "Heart failure", "sp_chrnkidn": "Chronic kidney disease",
    "sp_cncr": "Cancer", "sp_copd": "COPD", "sp_depressn": "Depression", "sp_diabetes": "Diabetes",
    "sp_ischmcht": "Ischemic heart disease", "sp_osteoprs": "Osteoporosis", "sp_ra_oa": "Rheumatoid / osteoarthritis",
    "sp_strketia": "Stroke / TIA",
}

COST_FEATURE_LABELS = {
    "age": "Age", "sex": "Sex", "race": "Race", "esrd": "End-stage renal disease", "state": "State",
    "partd_months": "Part D (drug) coverage months", "n_chronic": "Number of chronic conditions",
    "ip_cost": "Last year's inpatient cost", "op_cost": "Last year's outpatient cost",
    "car_cost": "Last year's physician cost", "rx_cost": "Last year's drug cost", "ip_stays": "Hospital stays last year",
    "ip_days": "Hospital days last year", "op_claims": "Outpatient visits last year",
    "car_claims": "Physician claims last year", "rx_fills": "Prescription fills last year",
    "rx_distinct_ndc": "Distinct drugs last year", "dx3_distinct": "Distinct diagnoses last year",
    **CHRONIC_LABELS,
}


def category_for(code: str, kind: str) -> str:
    if kind == "drg":
        return "inpatient"
    if code[:1].isalpha():
        return {"J": "drug", "E": "dme", "K": "dme", "A": "transport", "G": "other"}.get(code[0], "other")
    n = int(code) if code.isdigit() else 0
    if 70000 <= n <= 79999:
        return "imaging"
    if 10000 <= n <= 69999:
        return "surgery"
    if 80000 <= n <= 89999:
        return "lab"
    return "medicine"


def label(code: str | None, kind: str = "hcpcs") -> str | None:
    if not code:
        return None
    return {"hcpcs": HCPCS, "drg": DRG, "icd9": ICD9}[kind].get(code)
