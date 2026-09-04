"""Write role-contact YAML next to a tailored CV."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.role_contacts.models import RoleContactReport


def write_contacts_yaml(report: RoleContactReport, output_path: Path) -> Path:
    """Serialize a contact report with stable key order."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(
        report.to_mapping(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    output_path.write_text(payload, encoding="utf-8")
    return output_path.resolve()
