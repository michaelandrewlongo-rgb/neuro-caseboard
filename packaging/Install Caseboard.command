#!/bin/bash
# Double-click this to install Neuro-Caseboard on your Mac.
# (If macOS says "unidentified developer": right-click this file -> Open -> Open.)
cd "$(dirname "$0")" || { echo "Could not find the bundle folder."; read -r; exit 1; }

clear
cat <<'BANNER'
  ┌────────────────────────────────────────────────────────────┐
  │   Installing Neuro-Caseboard                                │
  │                                                            │
  │   • Takes about 10–15 minutes.                             │
  │   • Needs Wi-Fi (it downloads Python libraries).           │
  │   • You can keep using your Mac while it runs.             │
  │                                                            │
  │   Just wait until you see  ✅ INSTALLED  at the bottom.     │
  └────────────────────────────────────────────────────────────┘

BANNER

# Make sure the helper scripts can run even if the drive dropped the executable bit.
chmod +x ./setup-mac.sh ./bin/uv 2>/dev/null || true

if bash ./setup-mac.sh; then
  echo
  echo "  ✅ INSTALLED — look for the 'Caseboard' shortcut on your Desktop."
  echo "     Double-click it any time to start. You can unplug the drive now."
else
  echo
  echo "  ⚠️  The install hit a problem (see the messages above)."
  echo "     Copy the last ~15 lines and send them over and I'll sort it out."
fi

echo
read -r -p "  Press Return to close this window. "
