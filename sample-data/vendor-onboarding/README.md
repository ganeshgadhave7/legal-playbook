# Acme Demo Bank vendor-onboarding sample corpus

These six DOCX files are **entirely fictional** and intended only for the Acme Demo Bank portfolio application. The bank, vendor, people, report status, test results, and control statements are invented. None of the vendor evidence is a real SOC 2 report, ISO certificate, penetration-test report, or compliance attestation.

## Documents and upload metadata

| File | Suggested title | Department | Type | Code | Version |
|---|---|---|---|---|---|
| `01_TPRM_STD_001_Third_Party_IT_Risk_Assessment_Standard.docx` | Third-Party IT Risk Assessment Standard | Third-Party Risk | Internal risk standard | `TPRM-STD-001` | `1.0` |
| `02_SEC_STD_004_Third_Party_Security_and_Data_Handling_Requirements.docx` | Third-Party Information Security and Data Handling Requirements | Information Security | Internal security standard | `SEC-STD-004` | `1.0` |
| `03_BCM_STD_006_Third_Party_Resilience_and_Incident_Requirements.docx` | Third-Party Resilience, Recovery, and Incident Requirements | Business Continuity | Internal resilience standard | `BCM-STD-006` | `1.0` |
| `04_VND_NSTAR_INTAKE_001_Service_and_Data_Flow_Questionnaire.docx` | IT Vendor Service and Data-Flow Questionnaire — Northstar Demo Systems | Third-Party Risk | Vendor due-diligence questionnaire | `VND-NSTAR-INTAKE-001` | `1.0` |
| `05_VND_NSTAR_SEC_002_Security_Assurance_and_Test_Summary.docx` | Vendor Security Assurance and Testing Summary — Northstar Demo Systems | Information Security | Vendor self-attestation and evidence index | `VND-NSTAR-SEC-002` | `1.0` |
| `06_VND_NSTAR_BCM_003_Business_Continuity_and_Incident_Response_Summary.docx` | Business Continuity and Incident Response Summary — Northstar Demo Systems | Business Continuity | Vendor resilience questionnaire response | `VND-NSTAR-BCM-003` | `1.0` |

Mark each upload as **Fictional demo document**. Upload the three internal standards first, then the three Northstar evidence files. Approve and index each document before testing retrieval.

## Deliberate gaps for testing

The synthetic vendor processes Restricted customer identity data and supports account opening, so the bank's risk policy puts it in the High tier. The evidence packet intentionally contains reviewable gaps: no independent SOC 2 report supplied, an old penetration test with an open finding, emergency-account MFA exceptions, 180-day logs, a seven-day critical-patching target, 45-day active-data deletion, an 8-hour/4-hour RTO/RPO, an old partial recovery test, and a 72-hour incident-notice term. The fictional bank standards define stronger requirements so the playbook can find and cite the mismatches.

The model should report these as evidence gaps, cite the relevant source sections, and recommend human review; it must not claim that the vendor is certified or that the documents establish real regulatory compliance.
