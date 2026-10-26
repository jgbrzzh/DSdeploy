"""Test-only bridge: Windows launcher -> Docker in the disposable WSL distro.

No Docker behavior is mocked. Only Windows filesystem arguments are translated.
"""
import re
import os
import subprocess
import sys

args = []
for arg in sys.argv[1:]:
    if re.match(r"^[A-Za-z]:[\\/]", arg):
        arg = "/mnt/" + arg[0].lower() + "/" + arg[3:].replace("\\", "/")
    args.append(arg)
distro = os.environ.get("DSDEPLOY_TEST_DISTRO")
if not distro:
    raise SystemExit("Set DSDEPLOY_TEST_DISTRO to an explicitly created disposable WSL distribution.")
sys.exit(subprocess.call(["wsl.exe", "-d", distro, "-u", "root", "--exec", "docker", *args]))
