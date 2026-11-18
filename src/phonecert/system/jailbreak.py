"""Jailbreak hints.

Nothing runs on the phone, so this is inference from what lockdown services
expose: installed apps (installation_proxy) and crash-report file names.
A clean result is NOT proof — a rootless jailbreak with its store removed
can hide. A positive result is strong evidence.
"""

# Package managers, jailbreak tools and sideload helpers (bundle ids, lower-case).
KNOWN_BUNDLES = {
    "com.saurik.cydia": "Cydia",
    "org.coolstar.sileostore": "Sileo",
    "org.coolstar.sileonightly": "Sileo (nightly)",
    "xyz.willy.zebra": "Zebra",
    "com.opa334.dopamine": "Dopamine",
    "com.opa334.trollstore": "TrollStore",
    "com.opa334.trollstorepersistencehelper": "TrollStore helper",
    "org.palera1n.palera1n": "palera1n",
    "com.palera1n.palera1n": "palera1n",
    "science.xnu.undecimus": "unc0ver",
    "com.electrateam.chimera": "Chimera",
    "com.electrateam.odyssey": "Odyssey",
    "org.coolstar.electra": "Electra",
    "com.checkra1n.loader": "checkra1n",
    "ru.serenity.serotonin": "Serotonin",
    "com.hackyouriphone.installer": "Installer",
    "com.altstore.altstore": "AltStore",
    "com.sidestore.sidestore": "SideStore",
}

# Process names of jailbreak daemons that show up in crash report file names.
CRASH_TOKENS = ("jailbreakd", "substrate", "substitute", "ellekit", "dopamine",
                "palera1n", "launchd_jb", "cydia", "sileo", "trollstore")

# Apple-signed distribution channels. Anything else (dev / enterprise certificate) was sideloaded.
LEGIT_SIGNERS = ("Apple iPhone OS Application Signing", "TestFlight Beta Distribution")


def _sideloaded(bundle_id: str, info: dict) -> bool:
    signer = info.get("SignerIdentity") or ""
    return bool(signer) and signer not in LEGIT_SIGNERS


def analyse(apps: dict, crash_files: list) -> dict:
    found = [f"{name} ({bid})" for bid, name in KNOWN_BUNDLES.items() if bid in {k.lower() for k in apps}]
    sideloaded = sorted(
        f"{info.get('CFBundleDisplayName') or info.get('CFBundleName') or bid} ({bid})"
        for bid, info in apps.items() if _sideloaded(bid, info)
    )
    crash_hits = sorted({f.rsplit("/", 1)[-1] for f in crash_files
                         if any(t in f.lower() for t in CRASH_TOKENS)})

    if found or crash_hits:
        verdict = "likely"
    elif sideloaded:
        verdict = "suspicious"   # dev-signed apps: common with jailbreaks, but also with honest developers
    else:
        verdict = "none"
    return {
        "verdict": verdict,
        "jailbreak_apps": found,
        "sideloaded_apps": sideloaded,
        "crash_hints": crash_hits,
        "user_app_count": len(apps),
    }
