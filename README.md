# MUTCD Warrant Pro

A traffic signal warrant analysis tool implementing all 9 warrants from the MUTCD 2009 Edition; the 2023 Edition is not used in this version to ensure complete, verified implementation of all warrant logic.

---

## Features

- **All 9 MUTCD Warrants** — Eight-Hour Volume, Four-Hour Volume, Peak Hour, Pedestrian Volume, School Crossing, Coordinated Signal System, Crash Experience, Roadway Network, Grade Crossing
- **Automatic major/minor street assignment** based on traffic volumes
- **70% threshold reduction** automatically applied (speed >40 mph or population <10,000; Warrant 4 uses >35 mph)
- **Interactive charts** with pass/fail visualization for each warrant
- **Export options** — PDF report, Excel workbook, CSV summary

---

## Installation

```bash
pip install streamlit plotly pandas reportlab openpyxl
```

---

## Usage

1. Run the app:
   ```bash
   streamlit run app.py
   ```

2. Enter project details and traffic counts

3. Click **Run Analysis** to evaluate all warrants

4. Export results as PDF, Excel, or CSV

---

## Tech Stack

- Python
- Streamlit
- Plotly
- Pandas
- ReportLab (PDF generation)
- OpenPyXL (Excel export)

---

## Reference

Based on the **Manual on Uniform Traffic Control Devices (MUTCD) 2009 Edition**, published by FHWA.

---

## Disclaimer

This tool assists with signal warrant analysis only.
All results must be verified by a licensed Professional Engineer before use in design or decision-making.

---

## License

Free to use and adapt for internal business, personal, or educational use.
Not permitted for resale or inclusion in paid products.

Licensed under Creative Commons Attribution–NonCommercial 4.0 (CC BY-NC 4.0).

---

## Feedback

Found a bug or have a suggestion? Send feedback to contact@alexengineered.com

---

## Author

AlexEngineered

---

*Built for civil engineers who value their time.*