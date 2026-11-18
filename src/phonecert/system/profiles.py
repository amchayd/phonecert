"""Configuration profiles and MDM enrolment (`pymobiledevice3 profile list`).

An MDM profile means an organisation can lock, wipe or restrict the phone remotely.
A used phone offered for sale should have none.
"""


def analyse(raw: dict) -> dict:
    ids = list(raw.get("OrderedIdentifiers") or [])
    manifest = raw.get("ProfileManifest") or {}
    names = []
    mdm = False
    for pid in ids:
        meta = (raw.get("ProfileMetadata") or {}).get(pid) or manifest.get(pid) or {}
        name = meta.get("PayloadDisplayName") or pid
        names.append(name)
        blob = (pid + " " + str(meta)).lower()
        if "mdm" in blob or "com.apple.mdm" in blob or "device management" in blob:
            mdm = True
    return {"count": len(ids), "profiles": names, "mdm_enrolled": mdm,
            "verdict": "mdm" if mdm else ("profiles" if ids else "clean")}
