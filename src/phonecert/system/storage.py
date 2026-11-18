"""Storage used / total, from the lockdown domain com.apple.disk_usage (values in bytes).

TotalDiskCapacity is the raw NAND size (128000000000 on a 128 GB iPhone 13);
TotalDataCapacity is the user data partition.
Two "available" figures exist and differ hugely when iCloud Photos optimisation is on:
  AmountDataAvailable  what Settings → iPhone Storage calls free (0.94 GB on the test iPhone 13)
  TotalDataAvailable   free + purgeable caches (97 GB on the same phone)
"Used" follows Settings: total minus AmountDataAvailable. Purgeable is reported separately.
"""

# Marketed capacities Apple has shipped on iPhones, in GB.
MARKETED_GB = (16, 32, 64, 128, 256, 512, 1024, 2048)


def marketed_capacity_gb(total_bytes):
    """Map the raw disk size to the capacity printed on the box (127.9 GB → 128)."""
    if not total_bytes:
        return None
    gb = total_bytes / 1e9
    return min(MARKETED_GB, key=lambda m: abs(m - gb))


def analyse(raw: dict) -> dict:
    total = raw.get("TotalDiskCapacity")
    free = raw.get("AmountDataAvailable")
    if free is None:
        free = raw.get("TotalDataAvailable")  # older dumps / if the key ever disappears
    with_purgeable = raw.get("TotalDataAvailable")
    used = total - free if total is not None and free is not None else None
    purgeable = with_purgeable - free if with_purgeable is not None and free is not None else None
    gb = lambda b: round(b / 1e9, 1) if b is not None else None
    return {
        "capacity_gb": marketed_capacity_gb(total),
        "total_gb": gb(total),
        "used_gb": gb(used),
        "free_gb": gb(free),
        "purgeable_gb": gb(purgeable),
        "used_pct": round(used / total * 100) if used is not None and total else None,
    }
