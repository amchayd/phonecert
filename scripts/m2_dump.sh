#!/usr/bin/env bash
# M2 research: dump everything pymobiledevice3 can read from the connected
# iPhone into reports/research/<serial>/ so we can look for component serials
# (battery, display, camera, Face ID…) without installing anything on the phone.
#
#   source .venv/bin/activate && scripts/m2_dump.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PMD=pymobiledevice3

# Wait for a paired device: poll usbmux until it lists one (Ctrl+C to give up).
get_serial() {  # `lockdown get KEY` would read a domain called KEY, so parse `lockdown info`
  $PMD lockdown info 2>/dev/null | grep -oE '"SerialNumber": "[^"]+"' | cut -d'"' -f4
}
while [ "$($PMD usbmux list 2>/dev/null)" = "[]" ] || ! serial=$(get_serial); do
  echo "⏳ no iPhone detected — plug it in, unlock it, tap 'Trust' (retrying in 3 s)"
  sleep 3
done
[ -n "$serial" ] || { echo "❌ device found but SerialNumber is empty"; exit 1; }
out="reports/research/$serial"; mkdir -p "$out"
echo "📱 $serial → $out"

run() {  # run <file> <args...>: save stdout, report size or error
  local f="$out/$1"; shift
  if "$PMD" "$@" > "$f" 2> "$f.err"; then
    rm -f "$f.err"; printf "  ✅ %-45s %8s bytes\n" "$1 ${*:2}" "$(wc -c < "$f")"
  else
    printf "  ❌ %-45s %s\n" "$1 ${*:2}" "$(grep -o 'ERROR .*' "$f.err" | tail -1)"; rm -f "$f"
  fi
}

run lockdown_info.json      lockdown info
run diag_info.json          diagnostics info
run ioreg_IOService.json    diagnostics ioregistry --plane IOService
run ioreg_IODeviceTree.json diagnostics ioregistry --plane IODeviceTree
run mobilegestalt.json      diagnostics mg
run battery.json            diagnostics battery single

for d in com.apple.mobile.battery com.apple.disk_usage.factory com.apple.mobile.internal \
         com.apple.xcode.developerdomain com.apple.international com.apple.mobile.restriction \
         com.apple.mobile.user_preferences com.apple.mobile.iTunes com.apple.mobile.backup \
         com.apple.mobile.wireless_lockdown com.apple.fairplay com.apple.mobile.chaperone \
         com.apple.mobile.software_behavior com.apple.mobile.debug com.apple.purplebuddy \
         com.apple.mobile.nikita com.apple.springboard com.apple.mobile.lockdown_cache \
         com.apple.mobile.sync_data_class com.apple.mobile.third_party_termination \
         com.apple.mobile.activation com.apple.mobile.data_sync com.apple.mobile.tethered_sync; do
  run "lockdown_$d.json" lockdown get "$d"
done

echo; echo "🔎 serial-looking keys across all dumps:"
grep -ohE '"[A-Za-z0-9_-]*([Ss]erial|SerialNumber|Lifetime|Calibration|Pearl|Display|Camera|Touch|NAND)[A-Za-z0-9_-]*"' "$out"/*.json \
  | sort | uniq -c | sort -rn | head -40
