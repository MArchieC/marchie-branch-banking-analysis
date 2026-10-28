"""One command to run every cleaner Python script in order."""

import importlib

STEPS = [
    "01_clean_institutions",
    "02_clean_financials",
    "03_clean_failures",
    "04_clean_complaints",
    "05_build_crosswalk",
    "06_clean_macro",
    "07_data_quality",
]

def main():
    for step in STEPS:
        print(f"--- {step} ---")
        #importlib allows Python to dynamically look up and import file using string variable.
        module = importlib.import_module(step)
        module.main()

if __name__ == "__main__":
    main()