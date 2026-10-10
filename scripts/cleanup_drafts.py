"""Keep only the latest draft case, delete old playbook versions, and republish the current playbook."""
import sys

import requests

BASE = "https://legal-playbook-production.up.railway.app"
EMAIL = "admin@acme.demo"
PASSWORD = "AcmeDemo2025!"


def get_token() -> str:
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print("Login failed:", r.status_code, r.text)
        sys.exit(1)
    return r.json()["access_token"]


def main() -> None:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Delete all cases except the latest one
    cases = requests.get(f"{BASE}/api/v1/playbooks/cases?limit=100", headers=headers).json()
    items = sorted(cases["items"], key=lambda x: x["created_at"], reverse=True)
    if not items:
        print("No cases to clean up.")
    else:
        latest = items[0]
        print(f"Keeping latest case: {latest['case_id']} ({latest['playbook_title']})")
        for c in items[1:]:
            r = requests.delete(f"{BASE}/api/v1/playbooks/cases/{c['case_id']}", headers=headers)
            if r.status_code == 204:
                print(f"Deleted case: {c['case_id']}")
            else:
                print(f"Failed to delete case {c['case_id']}: {r.status_code} {r.text}")

    # Manage playbooks
    playbooks = requests.get(f"{BASE}/api/v1/playbooks?limit=100", headers=headers).json()
    bank_playbooks = [p for p in playbooks["items"] if p["key"] == "bank_it_vendor_onboarding"]
    for p in bank_playbooks:
        if p["version"] == "1.0":
            r = requests.delete(f"{BASE}/api/v1/playbooks/bank_it_vendor_onboarding?version=1.0", headers=headers)
            if r.status_code == 204:
                print("Deleted archived playbook v1.0")
            else:
                print(f"Failed to delete v1.0: {r.status_code} {r.text}")
        elif p["version"] == "2.0" and p["status"] != "published":
            r = requests.put(
                f"{BASE}/api/v1/playbooks/bank_it_vendor_onboarding",
                headers=headers,
                json={"status": "published"},
            )
            if r.status_code == 200:
                print("Republished playbook v2.0")
            else:
                print(f"Failed to republish v2.0: {r.status_code} {r.text}")


if __name__ == "__main__":
    main()
