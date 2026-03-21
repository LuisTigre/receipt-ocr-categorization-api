"""
Orchestrator Script - Runs the full pipeline sequentially
1. Extract receipt images → JSON (image-json-converter.py)
2. Categorize products (prod_cat_cloud.py)
3. Cleanup (optional)
"""

import subprocess
import sys
from pathlib import Path

# =========================
# CONFIGURATION
# =========================
BASE_DIR = Path(__file__).parent
SCRIPTS = [
    ("Extraction", "image-json-converter.py"),
    ("Categorization", "prod_cat_cloud.py"),   
]

# =========================
# RUN SCRIPT
# =========================
def run_script(name, script_file):
    """Run a Python script and return success status"""
    script_path = BASE_DIR / script_file
    
    if not script_path.exists():
        print(f"✗ [ERROR] {script_file} not found!")
        return False
    
    print(f"\n{'='*60}")
    print(f"[STEP] Running {name}: {script_file}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=BASE_DIR,
            check=True,
            text=True
        )
        print(f"\n✓ [{name.upper()}] Completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ [{name.upper()}] Failed with error!")
        return False
    except Exception as e:
        print(f"\n✗ [{name.upper()}] Unexpected error: {e}")
        return False

# =========================
# MAIN PIPELINE
# =========================
def main():
    print("\n" + "="*60)
    print("RECEIPT AI - FULL PIPELINE ORCHESTRATOR")
    print("="*60)
    
    failed_steps = []
    
    for name, script_file in SCRIPTS:
        success = run_script(name, script_file)
        if not success:
            failed_steps.append(name)
            print(f"\n[WARN] Stopping pipeline due to {name} failure")
            break
    
    # Final summary
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    
    if not failed_steps:
        print("✓ All steps completed successfully!")
        print(f"\nResults in: output_json/")
        return 0
    else:
        print(f"✗ Failed steps: {', '.join(failed_steps)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
