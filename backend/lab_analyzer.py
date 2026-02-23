"""
lab_analyzer.py — Smart lab report value extraction and analysis.
Parses common blood test values from raw text, compares against normal ranges,
and flags abnormal results.
"""

import re


# Normal ranges (approximate, for general adult reference)
NORMAL_RANGES = {
    "hemoglobin": {"unit": "g/dL", "male": (13.5, 17.5), "female": (12.0, 16.0), "default": (12.0, 17.5),
                   "patterns": [r"h(?:ae)?moglobin[:\s]*(\d+\.?\d*)", r"hgb[:\s]*(\d+\.?\d*)", r"hb[:\s]*(\d+\.?\d*)"]},
    "rbc": {"unit": "million/µL", "male": (4.7, 6.1), "female": (4.2, 5.4), "default": (4.2, 6.1),
            "patterns": [r"rbc[:\s]*(\d+\.?\d*)", r"red\s*blood\s*cell[s]?[:\s]*(\d+\.?\d*)"]},
    "wbc": {"unit": "cells/µL", "default": (4500, 11000),
            "patterns": [r"wbc[:\s]*(\d+\.?\d*)", r"white\s*blood\s*cell[s]?[:\s]*(\d+\.?\d*)", r"leucocyte[s]?[:\s]*(\d+\.?\d*)"]},
    "platelets": {"unit": "/µL", "default": (150000, 400000),
                  "patterns": [r"platelet[s]?[:\s]*(\d+\.?\d*)", r"plt[:\s]*(\d+\.?\d*)"]},
    "glucose_fasting": {"unit": "mg/dL", "default": (70, 100),
                        "patterns": [r"fasting\s*(?:blood\s*)?(?:glucose|sugar|fbs)[:\s]*(\d+\.?\d*)", r"fbs[:\s]*(\d+\.?\d*)"]},
    "glucose_random": {"unit": "mg/dL", "default": (70, 140),
                       "patterns": [r"random\s*(?:blood\s*)?(?:glucose|sugar|rbs)[:\s]*(\d+\.?\d*)", r"rbs[:\s]*(\d+\.?\d*)",
                                    r"blood\s*sugar[:\s]*(\d+\.?\d*)", r"glucose[:\s]*(\d+\.?\d*)"]},
    "hba1c": {"unit": "%", "default": (4.0, 5.7),
              "patterns": [r"hba1c[:\s]*(\d+\.?\d*)", r"a1c[:\s]*(\d+\.?\d*)", r"glycated\s*h(?:ae)?moglobin[:\s]*(\d+\.?\d*)"]},
    "cholesterol_total": {"unit": "mg/dL", "default": (0, 200),
                          "patterns": [r"total\s*cholesterol[:\s]*(\d+\.?\d*)", r"cholesterol[:\s]*(\d+\.?\d*)"]},
    "hdl": {"unit": "mg/dL", "default": (40, 100),
            "patterns": [r"hdl[:\s]*(\d+\.?\d*)"]},
    "ldl": {"unit": "mg/dL", "default": (0, 130),
            "patterns": [r"ldl[:\s]*(\d+\.?\d*)"]},
    "triglycerides": {"unit": "mg/dL", "default": (0, 150),
                      "patterns": [r"triglyceride[s]?[:\s]*(\d+\.?\d*)"]},
    "creatinine": {"unit": "mg/dL", "default": (0.6, 1.2),
                   "patterns": [r"creatinine[:\s]*(\d+\.?\d*)"]},
    "urea": {"unit": "mg/dL", "default": (7, 20),
             "patterns": [r"urea[:\s]*(\d+\.?\d*)", r"bun[:\s]*(\d+\.?\d*)"]},
    "sgpt": {"unit": "U/L", "default": (7, 56),
             "patterns": [r"sgpt[:\s]*(\d+\.?\d*)", r"alt[:\s]*(\d+\.?\d*)"]},
    "sgot": {"unit": "U/L", "default": (10, 40),
             "patterns": [r"sgot[:\s]*(\d+\.?\d*)", r"ast[:\s]*(\d+\.?\d*)"]},
    "tsh": {"unit": "mIU/L", "default": (0.4, 4.0),
            "patterns": [r"tsh[:\s]*(\d+\.?\d*)", r"thyroid\s*stimulating[:\s]*(\d+\.?\d*)"]},
    "vitamin_d": {"unit": "ng/mL", "default": (20, 50),
                  "patterns": [r"vitamin\s*d[:\s]*(\d+\.?\d*)", r"vit\.?\s*d[:\s]*(\d+\.?\d*)"]},
    "vitamin_b12": {"unit": "pg/mL", "default": (200, 900),
                    "patterns": [r"vitamin\s*b12[:\s]*(\d+\.?\d*)", r"vit\.?\s*b12[:\s]*(\d+\.?\d*)", r"b12[:\s]*(\d+\.?\d*)"]},
    "iron": {"unit": "µg/dL", "default": (60, 170),
             "patterns": [r"(?:serum\s*)?iron[:\s]*(\d+\.?\d*)"]},
    "calcium": {"unit": "mg/dL", "default": (8.5, 10.5),
                "patterns": [r"calcium[:\s]*(\d+\.?\d*)"]},
    "uric_acid": {"unit": "mg/dL", "default": (3.4, 7.0),
                  "patterns": [r"uric\s*acid[:\s]*(\d+\.?\d*)"]},
}


def analyze_report(text: str, gender: str = "default") -> list[dict]:
    """
    Parse lab report text and extract values.
    Returns a list of findings with status (normal/high/low).
    """
    text_lower = text.lower()
    findings = []

    for test_name, info in NORMAL_RANGES.items():
        for pattern in info["patterns"]:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    value = float(match.group(1))
                except ValueError:
                    continue

                # Use gender-specific range if available
                range_key = gender if gender in info else "default"
                low, high = info[range_key]

                if value < low:
                    status = "LOW"
                    flag = "⬇️"
                elif value > high:
                    status = "HIGH"
                    flag = "⬆️"
                else:
                    status = "NORMAL"
                    flag = "✅"

                display_name = test_name.replace("_", " ").title()
                findings.append({
                    "test": display_name,
                    "value": value,
                    "unit": info["unit"],
                    "normal_range": f"{low}-{high}",
                    "status": status,
                    "flag": flag,
                })
                break  # Only match first pattern for each test

    return findings


def format_findings(findings: list[dict]) -> str:
    """Format findings into a readable context string for the LLM."""
    if not findings:
        return ""

    lines = ["--- LAB REPORT ANALYSIS ---"]
    abnormal_count = sum(1 for f in findings if f["status"] != "NORMAL")

    for f in findings:
        lines.append(
            f"{f['flag']} {f['test']}: {f['value']} {f['unit']} "
            f"(Normal: {f['normal_range']}) — {f['status']}"
        )

    if abnormal_count > 0:
        lines.append(f"\n⚠️ {abnormal_count} value(s) are outside normal range.")
    else:
        lines.append("\n✅ All detected values are within normal range.")

    return "\n".join(lines)
