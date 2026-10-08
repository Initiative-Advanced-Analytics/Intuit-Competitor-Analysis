"""Run the whole Method 2 pipeline in order.

    python "2. Scripts/run_all.py"

Each step depends on the one before it. The last step is the verification
suite - if that does not come back clean, do not use the numbers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    ("stack_actuals.py", "Stacking Intuit's actual spend"),
    ("m2_rolling_factor.py", "Building the rolling quarterly factors"),
    ("build_m2_outputs.py", "Applying Method 2 and writing the datasets"),
    ("build_client_view.py", "Building the client-facing Excel"),
    ("verify_m2.py", "Verification suite"),
]


def main() -> int:
    print("Rebuilding Method 2 outputs\n")
    for index, (script, description) in enumerate(STEPS, start=1):
        print(f"[{index}/{len(STEPS)}] {description}")
        result = subprocess.run(
            [sys.executable, str(HERE / script)], cwd=HERE,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-12:]
            print(f"\n  FAILED in {script}:\n")
            for line in tail:
                print(f"    {line}")
            if "Permission denied" in (result.stderr or ""):
                blocked = [
                    token.strip("'\"")
                    for token in (result.stderr or "").split()
                    if token.strip("'\"").endswith((".xlsx", ".docx", ".csv"))
                ]
                name = Path(blocked[-1]).name if blocked else "an output file"
                print(
                    f"\n  '{name}' is open in Excel or Word, so it cannot be"
                    "\n  overwritten. Close it and rerun."
                )
            return 1
        if script in ("build_m2_outputs.py", "build_client_view.py", "verify_m2.py"):
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
        print()
    print("Done. Outputs are in '3. Outputs'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
