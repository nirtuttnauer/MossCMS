#!/usr/bin/env python3
"""Calculate a transparent self-hosting example from dated quotes and explicit assumptions."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def amount(values, key):
    try:
        value = Decimal(str(values[key]))
    except (InvalidOperation, KeyError) as error:
        raise ValueError(f"Missing or invalid cost input: {key}") from error
    if not value.is_finite() or value < 0:
        raise ValueError(f"Cost inputs must be finite and nonnegative: {key}")
    return value


def calculate(values):
    compute = amount(values, "compute_monthly_usd")
    backups = compute * amount(values, "snapshot_backup_fraction")
    storage = amount(values, "object_storage_base_usd") + max(
        Decimal(0), amount(values, "object_storage_gib") - amount(values, "included_object_storage_gib")
    ) * amount(values, "extra_object_storage_usd_per_gib")
    transfer = max(
        Decimal(0), amount(values, "object_transfer_gib") - amount(values, "included_object_transfer_gib")
    ) * amount(values, "extra_object_transfer_usd_per_gib")
    compute_transfer = max(
        Decimal(0), amount(values, "compute_transfer_gib") - amount(values, "included_compute_transfer_gib")
    ) * amount(values, "extra_compute_transfer_usd_per_gib")
    labor = amount(values, "operator_hours_monthly") * amount(values, "operator_hourly_usd")
    other = amount(values, "other_monthly_usd")
    infrastructure = compute + backups + storage + transfer + compute_transfer + other
    items = {
        "software": Decimal(0),
        "computeAndDatabase": compute,
        "snapshotBackups": backups,
        "objectStorageAndBackups": storage,
        "objectTransferOverage": transfer,
        "computeTransferOverage": compute_transfer,
        "other": other,
        "infrastructure": infrastructure,
        "operatorTime": labor,
        "total": infrastructure + labor,
    }
    return {name: str(value.quantize(Decimal("0.01"))) for name, value in items.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    data = json.loads(args.inputs.read_text())
    try:
        result = calculate(data["inputs"])
    except (KeyError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "currency": "USD",
                "quotedAt": data["quoted_at"],
                "monthly": result,
                "assumptions": data["assumptions"],
                "sources": data["sources"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
