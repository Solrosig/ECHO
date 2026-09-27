"""Rebuild every figure of the report from its script, in report order. Run from this folder:
    python make_all_figures.py
Each figure can also be rebuilt on its own with its make_figure_<n>.py."""
import runpy, sys
from pathlib import Path

ORDER = ["4_1", "4_2", "4_3", "4_4", "4_5", "4_6", "4_7", "5_1", "5_2", "5_3", "5_4", "5_5", "5_6",
         "5_7", "5_8", "5_9", "5_10", "5_11", "E_1"]
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
for n in ORDER:
    script = here / f"make_figure_{n}.py"
    print(f"--- Figure {n.replace('_', '.')}")
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        print("skipped:", e)
