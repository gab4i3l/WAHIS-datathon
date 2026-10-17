# WAHIS Datathon — trends in animal disease occurrence

This repository analyses WOAH WAHIS **reported new outbreak counts from 2005–2024** for Challenge 6. It includes an audited data-processing and exploratory workflow, interpretable baseline models, time-ordered validation, presentation charts and a technical report.

Start with [the technical report](TECHNICAL_REPORT.md), [the executed EDA notebook](eda/part3_eda.ipynb), and [the detailed chart interpretations](eda/report.md).

## Reproduce the results

### 1. Obtain the repository and check the data

Run commands from this repository's root. Python **3.11 or later** is required; the recorded execution used Python 3.14 on macOS. All main-run input files are already included:

- `WAHIS_data.csv`: original mixed-grain WAHIS extract (about 86 MB); analysis restricts its years to 2005–2024.
- `data/climate_country_month.csv`: supplied country-month climate values.
- `data/wahis_country_iso3.csv`: supplied WAHIS country-to-ISO3 mapping.

No climate download or API credentials are needed for the main pipeline. Source data are read without modification. If a teammate supplies `data/cleaned_summary.csv`, it takes precedence over the raw extract; use an explicit input path below for an unambiguous reproduction of the supplied results. The recorded raw-data SHA-256 is in the technical report and `eda/output/audit.json`.

### 2. Create an environment and install dependencies

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The portable requirements allow compatible recent package versions. `eda/requirements-lock.txt` records the exact original environment; `eda/output/run_manifest.json` records the versions actually used by the latest complete pipeline run. The lock is an environment record, not a cross-platform guarantee.

### 3. Run processing, modelling and validation

```sh
python run_pipeline.py --input WAHIS_data.csv --summary-policy prefer-both
```

This command:

1. Runs all automated data-integrity and model-validation tests, failing before regeneration if a test fails.
2. Selects and validates summary counts, removes verified regional duplicates, and exports descriptive aggregates and charts.
3. Reconciles count totals across eight aggregation grains.
4. Fits three disease-region reporting baselines and evaluates them on common eligible 2019–2024 targets using earlier observations only.
5. Writes the technical report, model results and a provenance manifest with input/source hashes and package versions.

Allow a few minutes for the first run, including font-cache creation. The default command `python run_pipeline.py` automatically selects the cleaned export when it exists. To analyse a teammate export explicitly:

```sh
python run_pipeline.py --input data/cleaned_summary.csv --summary-policy prefer-both
```

To use only Both animal categories summaries, choose `--summary-policy both-only`. This changes the scope and regenerates the main reports and outputs under that policy. Rerun the explicit raw/prefer-both command above to restore the supplied result scope.

### 4. Refresh the notebook and run tests independently

```sh
python eda/execute_notebook.py
python -m unittest discover -s eda -p 'test_*.py'
```

The execution helper uses the active Python interpreter; a separately installed Jupyter application is unnecessary. It starts a local Jupyter kernel, so the environment must allow localhost communication. It refreshes the EDA notebook, not the modelling report. By default the notebook selects a cleaned export if present; set its `INPUT` to `ROOT / 'WAHIS_data.csv'` to match the explicit raw-data pipeline run when a cleaned export also exists. For interactive use, open the notebook in a compatible editor and select this environment's interpreter.

### 5. Inspect the generated deliverables

| Output | Contents |
| --- | --- |
| `TECHNICAL_REPORT.md` | Processing/model methods, results, interpretation, validation evidence and limitations |
| `eda/report.md` | Ten supported insights and explanations for each chart |
| `eda/part3_eda.ipynb` | Executed EDA notebook with figures and findings |
| `eda/output/charts/` | Twelve figures, each as 300-dpi PNG and editable SVG |
| `eda/output/tables/` | Annual, semester, disease, regional, country, anomaly and data-quality tables |
| `eda/output/modelling/predictions.csv` | Per-target predictions, observations and training cutoffs |
| `eda/output/modelling/metrics.csv` | Common-target errors for the three baseline models |
| `eda/output/modelling/metrics_by_series.csv` | Disease-region model errors |
| `eda/output/modelling/validation.json` | Evaluation eligibility, scope and time-window settings |
| `eda/output/audit.json` | Input checksum, summary selection, missingness and climate-join audit |
| `eda/output/run_manifest.json` | Full-run versions, hashes, tests and configuration |

Larger generated orphan and country-disease-year diagnostic tables are ignored by Git and recreated by the pipeline. No full derived dataset is committed or required.

## Methods and interpretation

**One source row is not necessarily one outbreak.** The CSV mixes summary counts, species details and outbreak-ID records. The pipeline sums only selected **New outbreaks** summary counts. It prefers Both animal categories within a disease/subtype/place/semester group, using existing category summaries only when a Both summary is absent. Unknown counts and absent reports are not inferred as zero. Original disease labels remain separate. See [the input contract](eda/README.md#input-contract) before using a cleaned export.

The modelling outcome is known reported counts per country with numeric disease summaries, **not disease incidence**. Seasonal persistence, a trailing five-year seasonal median and a log-linear trend are compared through an expanding-window evaluation. All use the same eligible targets, and each target is predicted from earlier semesters only. The exploratory anomaly screen uses a separate robust historical score; its flags are not validated epidemic detections or significance tests.

Key supplied-data findings include a 2011 peak heavily driven by Iran's American foulbrood summaries, changing reporting participation, and strong July–December concentration in reported bluetongue counts. Summary policy changes known totals from approximately 3.92 million (Both-only) to 4.71 million (category fallback included). Verify the extreme records and subtype additivity before drawing epidemiological conclusions. The technical report contains exact results and qualifications.

Monthly disease seasonality and occurrence-date modelling are unsupported because the disease extract has only reporting semesters. Both 2024 halves appear, but completeness cannot be confirmed. Climate joins establish data compatibility only; validated climate associations and operational early warnings remain follow-up work.

## Repository map and legacy work

- `run_pipeline.py`: complete audited reproduction entry point and technical-report generation.
- `eda/analysis.py`: summary selection, data validation, EDA, charts and detailed report.
- `eda/modelling.py`: model fitting and temporal validation.
- `eda/test_analysis.py`, `eda/test_modelling.py`: integrity and time-ordering tests.
- `eda/execute_notebook.py`: execute the EDA notebook using the active environment.
- `script.ipynb`: original team notebook, preserved unchanged; its preprocessing and model claims differ from the audited workflow. See the legacy review in the technical report.
- `prepare_climate.py`: optional original climate downloader and raster aggregation script.
- `worldclim_country_monthly.csv`, `worldclim_country_semester.csv`: additional supplied climate exports, not mixed into the audited join.

To inspect or rerun legacy work, install `requirements-legacy.txt`. Climate regeneration is optional, downloads approximately 1.2 GB, requires internet access, and overwrites the two climate/mapping outputs under `data/`:

```sh
python -m pip install -r requirements-legacy.txt
python prepare_climate.py
```

The legacy notebook includes missing-as-zero assumptions and full-series target thresholds that are unsuitable for the audited predictive validation. Its results are not reproduced or endorsed by `run_pipeline.py`. Original team files are preserved; the supported submission results are those linked above.
