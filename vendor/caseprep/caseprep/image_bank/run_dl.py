#!/usr/bin/env python3
"""Run debug_labeler with env."""
import subprocess, sys, os
env = os.environ.copy()
with open("/mnt/c/Users/Michael/Desktop/PAPERS/.env") as f:
    for line in f:
        line = line.strip().replace("\r", "")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
r = subprocess.run([sys.executable, "-m", "caseprep.image_bank.debug_labeler"], env=env,
                   cwd=os.path.expanduser("~/projects/caseprep"))
sys.exit(r.returncode)
