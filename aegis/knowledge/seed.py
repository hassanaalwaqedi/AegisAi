"""Idempotent command-line seed for approved Aegis creator/project knowledge."""

from __future__ import annotations

import argparse
import json

from aegis.knowledge.official_records import OFFICIAL_KNOWLEDGE
from aegis.knowledge.service import SeedFailed, get_system_knowledge_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed approved database-backed Aegis knowledge.")
    parser.add_argument("--force", action="store_true", help="Intentionally supersede existing records with a new official version.")
    args = parser.parse_args()
    try:
        report = get_system_knowledge_service().seed_official(OFFICIAL_KNOWLEDGE, force=args.force)
    except SeedFailed as exc:
        print(json.dumps(exc.report.as_dict(), sort_keys=True))
        return 1
    print(json.dumps(report.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
