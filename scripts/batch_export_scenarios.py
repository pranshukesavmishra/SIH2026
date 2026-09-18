"""
Export all 6 scenario telemetry runs efficiently (run once, copy to targets).
"""
import glob
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tools.export_telemetry import export

scenarios = [
    ("scenarios/iss_pass.yaml", "telemetry_iss_pass.json", 40.0),
    ("scenarios/leo_pass_nominal.yaml", "telemetry_leo_pass_nominal.json", 25.0),
    ("scenarios/turbulence_hard.yaml", "telemetry_turbulence_hard.json", 20.0),
    ("scenarios/decoy_field.yaml", "telemetry_decoy_field.json", 25.0),
    ("scenarios/uav_relay.yaml", "telemetry_uav_relay.json", 25.0),
    ("scenarios/static_easy.yaml", "telemetry_static_easy.json", 15.0),
]

for s_path, out_name, duration in scenarios:
    t0 = time.time()
    out_web = f"src/fsoc_pat/web/{out_name}"
    out_pub = f"public/{out_name}"
    
    # Check if already generated
    if Path(out_web).exists() and Path(out_web).stat().st_size > 10000 and out_name != "telemetry_run.json":
        shutil.copyfile(out_web, out_pub)
        print(f"Already exists: {out_name} ({Path(out_web).stat().st_size / 1024:.1f} KB)")
        continue

    print(f"Exporting {s_path} ({duration}s)...", flush=True)
    res = export(s_path, out_web, duration=duration)
    shutil.copyfile(out_web, out_pub)
    dt = time.time() - t0
    s = res["summary"]
    print(f"  Done in {dt:.1f}s: {s['frames']} frames, acq={s['acquisition_time_s']}s, lock={s['lock_retention_pct']}%, p50={s['pointing_error_urad']['p50']} urad")

# Set default telemetry_run.json
shutil.copyfile("src/fsoc_pat/web/telemetry_iss_pass.json", "src/fsoc_pat/web/telemetry_run.json")
shutil.copyfile("src/fsoc_pat/web/telemetry_iss_pass.json", "public/telemetry_run.json")
shutil.copyfile("src/fsoc_pat/web/telemetry_iss_pass.json", "docs/media/telemetry_run.json")
print("All scenarios exported successfully!")
