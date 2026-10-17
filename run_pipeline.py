"""Reproduce processing, EDA, baseline modelling, validation and technical report."""
from pathlib import Path
import argparse
import hashlib
from importlib import metadata
import json
import platform
import sys
import unittest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'eda'))


def markdown_table(frame):
    """No optional tabulate dependency required."""
    if frame.empty:
        return 'No eligible model evaluations; inspect validation.json.'
    rows=['| '+' | '.join(frame.columns)+' |','| '+' | '.join(['---']*len(frame.columns))+' |']
    for _,r in frame.iterrows():
        rows.append('| '+' | '.join(f'{v:.4f}' if isinstance(v,float) else str(v) for v in r)+' |')
    return '\n'.join(rows)


def technical_report(audit,findings,metrics,validation,tests_run):
    best=metrics.sort_values('rmse_log1p').iloc[0] if len(metrics) else None
    comparison=(f'On common eligible targets, **{best.model}** has the lowest pooled log-scale RMSE '
                f'({best.rmse_log1p:.4f}). This is a retrospective benchmark result, not evidence of '
                'calibrated anomaly thresholds or operational early-warning skill.') if best is not None else 'No targets satisfy the validation criteria.'
    return f'''# Technical report: trends in reported animal disease occurrence

## Objective and scope

WOAH Datathon, Challenge 6: describe reported disease trends and geographical variation in 2005–2024, and distinguish expected patterns from candidates for investigation. This report consolidates the executable processing, exploratory analysis, modelling and validation pipeline. The [chart-by-chart EDA report](eda/report.md) provides research questions, methods, observations, interpretations and limitations for all 12 figures.

## Data and provenance

Input: `{Path(audit['input']).name}`. SHA-256: `{audit['sha256']}`. Mode: {audit['input_mode']}. The input contains {audit['input_rows']:,} rows, including years beyond the analysis window. The reproducible run records input/source hashes, package versions and validation configuration in [the manifest](eda/output/run_manifest.json).

The repository also supplies monthly climate values and an ISO3 mapping. These support an audited climate join, not a claim of association. Regenerating climate rasters is an optional independent workflow; supplied climate tables suffice for the main run.

## Methods: processing and exploratory analysis

A selected record is an administrative-division × country × disease × source subtype × reporting-semester summary. **New outbreaks** is summed; species details, animal cases/deaths and outbreak/event IDs are not counted as separate outbreaks. Periods are reporting semesters; exact occurrence dates are unavailable.

The `{audit['policy']}` policy prefers Both animal categories within each subtype group, otherwise existing Domestic/Wild summary counts. An unknown count in a present category keeps the fallback group unknown. Missing categories are not assumed surveyed. Synthetic summaries are excluded when flagged. Regional copies are verified after assigning overlapping Middle East countries to one region. Conflicting summary keys are quarantined. Original disease labels and compound subtype strings are retained. Subtype additivity remains a data-dictionary assumption that must be confirmed before epidemiological conclusions.

Processing removed {audit['verified_duplicate_rows_removed']:,} verified duplicate rows. Selected groups with unknown counts: {audit['selected_unknown_groups']:,}; detail groups lacking a summary: {audit['detail_groups_without_summary']:,}; conflicting summary keys: {audit['conflicting_summary_keys_excluded']:,}. Unknowns and missing combinations are never imputed as zero. Known-count sums may therefore be partial.

Annual, half-year, disease, country and regional totals are exported with missingness and observed-country counts. Fixed-country early/late-window comparisons are sensitivity analyses. A trailing same-half baseline compares log1p(counts per observed country) against the median and scaled MAD of the previous five years. Scores above 3.5 are **exploratory flags**, not significance tests. Zero-MAD or incomplete-history periods are skipped.

## Methods: models and temporal validation

Three interpretable models predict **reported counts per country with numeric disease summaries** at disease × region × semester resolution:

1. **Seasonal persistence:** the preceding year's same-half observation.
2. **Seasonal median:** the median of the previous five same-half observations.
3. **Log-linear trend:** least squares of log1p(reported counts per observed country) on an intercept, continuous half-year time and a half-year indicator; inverse-transformed predictions are floored at zero. This is a log-scale baseline, not a Poisson/negative-binomial likelihood or an unbiased original-scale mean estimate.

The evaluation starts in 2019 and ends in 2024. At each target semester, models use only earlier observations; training expands after each observed test outcome. The initial available history ends in 2018. Eligible targets require at least 20 earlier complete-count semesters and all five immediately preceding same-half years. Current/test counts never determine coefficients or seasonal predictions. No random split, full-series target threshold, future climate value or future reporting outcome is used for fitting. New disease labels and sparse series may be ineligible.

All models score the **same targets**. Metrics are mean absolute error in known counts per observed country and root mean squared error of log1p(predicted) minus log1p(observed). Macro mean series log-RMSE gives each eligible disease-region series equal weight; pooled RMSE gives each target equal weight. No model tuning, confidence interval or p-value is claimed. Test-period ranking is descriptive evaluation, not an independent test of a winner selected on these same results.

Availability is inferred from the reporting period because actual publication timestamps are absent. The denominator describes the observed records rather than an exposure-adjusted disease rate. Validation is conditional on this observed panel and is not a real-time backtest with reporting delays.

## Results: supported exploratory insights

'''+ '\n\n'.join(f'{i}. {v}' for i,v in enumerate(findings,1))+f'''

## Results: model validation

Of {validation['available_complete_test_targets']:,} complete-count test-period targets, {validation['scored_common_targets']:,} satisfy the common history criteria across {validation['scored_series']:,} disease-region series. Excluded targets are not zero outcomes. Model outputs, per-target predictions and per-series metrics are in [output/modelling](eda/output/modelling/).

{markdown_table(metrics)}

{comparison}

## Interpretation and limitations

Reported counts are concentrated in particular diseases/countries and can be driven by extreme entries. Iran's 2011 American foulbrood summaries require source verification. Region totals and growth cannot be interpreted as comparable underlying risk without surveillance and animal-population denominators. Changing disease definitions, subtype aggregation, administrative coverage and reporter composition can create apparent trends. The Both-only policy sensitivity quantifies a material scope decision. Observed 2024 half-year labels with eligible numeric counts are {audit["observed_semesters_2024"]}; complete reporting and extraction cutoff remain unverified.

The anomaly screen highlights deviations from a short historical baseline, while validation measures how three reporting-pattern baselines predict later observed values. Neither validates anomaly flags as epidemics. Climate matches {audit['climate'].get('match_pct',0):.2f}% of observed country-semesters; shared territory/ISO3 mappings require review. Monthly disease seasonality, geospatial risk maps and causal climate effects are not established by these data.

## Validation and reproducibility evidence

The full run passes {tests_run} automated tests before analysis. Tests cover summary priority, regional copies, unknowns versus zeros, synthetic records, conflicts, absent periods, temporal leakage, common evaluation targets and missing-history exclusions. Aggregate totals reconcile across eight independent table grains. Validation predictions are checked to use only earlier training timestamps. Source data are read without mutation. The executed EDA notebook and charts are retained; `python run_pipeline.py` regenerates processing, modelling, validation and this report, and `python eda/execute_notebook.py` refreshes notebook outputs.

## Legacy notebook review

`script.ipynb` and `prepare_climate.py` remain intact as team work. The legacy notebook has regression and climate analyses, but is not the validated submission entry point: it creates synthetic zeros in an early cell, fills absent disease-period reports as zero later, drops all non-Middle-East copies rather than verified identical copies, and defines surge thresholds using the full series before a train/test split. Its in-sample anomaly thresholds, broad biological interpretations and climate/predictive claims are not carried into this report. Re-running it requires additional dependencies listed separately and does not reproduce the audited totals here.

## Next steps most relevant to Challenge 6

Confirm summary policy and subtype additivity; verify large source entries; reconcile renamed disease labels with a documented crosswalk; obtain disease-specific reporting and animal exposure denominators. Then fit overdispersed count models and assess residuals, serial dependence and multiple comparisons. Climate work should use complete semester joins, contiguous lags, country/half-year effects, training-only standardisation and time-ordered validation against strong disease-history baselines. Obtain occurrence dates and publication timestamps before claiming monthly patterns or operational early-warning skill.
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,help='Explicit cleaned summary CSV; otherwise cleaned export if present, else raw CSV.')
    parser.add_argument('--summary-policy',choices=['prefer-both','both-only'],default='prefer-both')
    args=parser.parse_args()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'eda'),pattern='test_*.py')
    tests_run=suite.countTestCases()
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise SystemExit('Validation tests failed; outputs were not regenerated.')
    from analysis import run
    from modelling import save_validation
    summaries,tables,audit,findings,_=run(args.input,policy=args.summary_policy)
    for name in ['annual','semester','region','country','disease','disease_region','region_year','disease_year']:
        if not abs(tables[name].outbreaks.sum()-summaries['count'].sum())<1e-6:
            raise AssertionError(f'Aggregate reconciliation failed: {name}')
    pred,metrics,_,validation=save_validation(tables['disease_region_semester'],ROOT/'eda/output/modelling')
    if len(pred) and not (pred.training_last_year*2+pred.training_last_half < pred.Year*2+pred.half).all():
        raise AssertionError('Temporal leakage in model predictions')
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    inputs=[Path(audit['input']),ROOT/'data/climate_country_month.csv',ROOT/'data/wahis_country_iso3.csv']
    sources=[Path(__file__),ROOT/'eda/analysis.py',ROOT/'eda/modelling.py',ROOT/'eda/test_analysis.py',ROOT/'eda/test_modelling.py']
    manifest={'python':platform.python_version(),'platform':platform.platform(),
              'packages':{name:metadata.version(name) for name in ['pandas','numpy','matplotlib','seaborn','scipy','nbformat','nbclient','ipykernel']},
              'inputs':{str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):digest(p) for p in inputs if p.exists()},
              'sources':{str(p.relative_to(ROOT)):digest(p) for p in sources},
              'summary_policy':args.summary_policy,'tests_passed':tests_run,'aggregate_grains_reconciled':8,
              'modelling':validation,'command':'python run_pipeline.py'+(' --input '+str(args.input) if args.input else '')+' --summary-policy '+args.summary_policy}
    (ROOT/'eda/output/run_manifest.json').write_text(json.dumps(manifest,indent=2))
    (ROOT/'TECHNICAL_REPORT.md').write_text(technical_report(audit,findings,metrics,validation,tests_run))
    print('\nModel validation:\n'+metrics.to_string(index=False))
    print('\nCompleted: TECHNICAL_REPORT.md; eda/report.md; eda/output/ (including modelling and manifest).')

if __name__=='__main__':main()
