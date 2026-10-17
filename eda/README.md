# Part 3 — exploratory disease occurrence

This directory is independent of the team's existing notebook and climate preparation script. `part3_eda.ipynb` is the executed analysis; `report.md` contains the findings, assumptions and chart interpretations. Charts are exported as 300-dpi PNG and editable SVG under `output/charts/`; aggregate and audit tables are under `output/tables/`. No full cleaned dataset is generated. Larger orphan and country–disease–year diagnostic tables are locally generated but git-ignored; all tables can be reproduced from the source CSV. Exact package versions used here are recorded in `requirements-lock.txt` (Python 3.14/macOS; `requirements.txt` supports other recent Python environments).

## Reproduce

From the repository root, with Python 3.11 or later:

```sh
python -m venv .venv-eda
.venv-eda/bin/python -m pip install -r eda/requirements.txt
.venv-eda/bin/python eda/analysis.py
```

The default input is `data/cleaned_summary.csv` if present, otherwise `WAHIS_data.csv` through the audited raw fallback. Set a different input explicitly:

```sh
.venv-eda/bin/python eda/analysis.py --input path/to/cleaned_summary.csv
```

Prefer **Both animal categories** summaries by subtype, with existing Domestic/Wild summaries as a fallback. For the stricter teammate summary-only selection:

```sh
.venv-eda/bin/python eda/analysis.py --summary-policy both-only --output /tmp/wahis-both-only
```

The default output regenerates `eda/report.md`. A custom `--output` directory receives its own `report.md` with links to its own charts, leaving the default report unchanged. Each report lists its active policy. Open the notebook in Jupyter and select this environment's Python kernel. The notebook discovers the project root from either the repository or `eda` directory; set `INPUT` and `POLICY` in its configuration cell for a different export. `execute_notebook.py` executes with the invoking interpreter and writes outputs into the existing notebook.

```sh
.venv-eda/bin/python eda/execute_notebook.py
.venv-eda/bin/python -m unittest discover -s eda -p 'test_*.py'
```

## Input contract

Use the original CSV column names: Year, Semester, World region, Country, Administrative Division, Disease, Serotype/Subtype/Genotype, Species, Animal Category, Outbreak_id, New outbreaks. Preserve the source subtype strings and the original `is_synthetic_summary` flag if synthetic rows were created. Dash/blank outbreak ID means a summary-report record; blank Species identifies summary counts. Unknown counts remain unknown. Exporting only Both rows discards the category fallback and changes the scope. Flags set to true are excluded; unflagged fabricated zeros cannot be identified from the CSV and must not be supplied.

A row is a summary count, not one outbreak. Sum **New outbreaks**, never species rows or animal counts. Verified regional copies are removed; inconsistent summary-key counts are quarantined. Unknown groups, missing periods and missing disease–region combinations are not filled with zero. Distinct subtype summary rows are retained, pending dictionary confirmation of additivity. Original disease labels remain separate rather than assuming historical taxonomic equivalence.

Coverage means countries with numeric selected summaries, not proven complete reporting. Tables include unknown-group counts. Six-month periods are the finest disease time unit in this source: monthly plots, occurrence-date analyses, maps without trustworthy boundaries/coordinates, and validated operational early warnings are skipped. The baseline is a trailing five-year same-half log-MAD screen with a descriptive cutoff, not a significance test. Climate is audited for complete six-month joins; no association is inferred from a successful join.

## Full submission workflow

The root [README](../README.md) documents `python run_pipeline.py`, which runs tests, processing/EDA, three baseline models, expanding-window temporal validation and the consolidated [technical report](../TECHNICAL_REPORT.md). `modelling.py` owns the models; `test_modelling.py` checks leakage and evaluation eligibility. The EDA notebook is refreshed separately and deliberately makes no model-performance claims.
