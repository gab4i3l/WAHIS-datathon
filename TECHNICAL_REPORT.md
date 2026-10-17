# Technical report: trends in reported animal disease occurrence

## Objective and scope

WOAH Datathon, Challenge 6: describe reported disease trends and geographical variation in 2005–2024, and distinguish expected patterns from candidates for investigation. This report consolidates the executable processing, exploratory analysis, modelling and validation pipeline. The [chart-by-chart EDA report](eda/report.md) provides research questions, methods, observations, interpretations and limitations for all 12 figures.

## Data and provenance

Input: `WAHIS_data.csv`. SHA-256: `3e858a8672a079667fad6ffb6ca72136ef3e766dcc5b96d95c95253a6911b184`. Mode: audited raw fallback; upstream export not present. The input contains 657,148 rows, including years beyond the analysis window. The reproducible run records input/source hashes, package versions and validation configuration in [the manifest](eda/output/run_manifest.json).

The repository also supplies monthly climate values and an ISO3 mapping. These support an audited climate join, not a claim of association. Regenerating climate rasters is an optional independent workflow; supplied climate tables suffice for the main run.

## Methods: processing and exploratory analysis

A selected record is an administrative-division × country × disease × source subtype × reporting-semester summary. **New outbreaks** is summed; species details, animal cases/deaths and outbreak/event IDs are not counted as separate outbreaks. Periods are reporting semesters; exact occurrence dates are unavailable.

The `prefer-both` policy prefers Both animal categories within each subtype group, otherwise existing Domestic/Wild summary counts. An unknown count in a present category keeps the fallback group unknown. Missing categories are not assumed surveyed. Synthetic summaries are excluded when flagged. Regional copies are verified after assigning overlapping Middle East countries to one region. Conflicting summary keys are quarantined. Original disease labels and compound subtype strings are retained. Subtype additivity remains a data-dictionary assumption that must be confirmed before epidemiological conclusions.

Processing removed 80,622 verified duplicate rows. Selected groups with unknown counts: 33; detail groups lacking a summary: 30,617; conflicting summary keys: 0. Unknowns and missing combinations are never imputed as zero. Known-count sums may therefore be partial.

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

1. The largest country-disease contribution in the peak year is Iran: Paenibacillus larvae (American foulbrood), 459,127 (66.7% of 2011 known counts). This source entry needs verification before an epidemiological explanation.

2. The highest annual known count is 2011 (688,141); this is a reported-count peak, not an incidence estimate.

3. Paenibacillus larvae (American foulbrood) leads the disease ranking (523,909); the top ten labels contribute 54.0% of known counts.

4. Middle East contributes the largest regional share (25.0%); regions are disjoint after verified duplicate removal.

5. Iran has the highest known country count (875,688); the top five countries contribute 41.0%.

6. Countries with numeric summary counts vary from 136 to 168 annually; coverage limits trend interpretation.

7. Category fallback adds 784,440 known counts beyond Both-only summaries (3,923,628); this sensitivity materially affects scope.

8. The trailing same-half log-MAD screen flags 467 of 6425 eligible disease-region-semesters; these are candidates for review, not validated significant changes.

9. Bluetongue has 92.7% of known counts in Jul–Dec; this is pooled half-year reporting asymmetry, not confirmed monthly onset seasonality.

10. ASF known totals increase from 1,353 in 2005–09 to 57,768 in 2020–24 (+4,169.6%). Only 1 country has numeric summaries in every comparison year: changing participation prevents a broad fixed-country trend claim.

## Results: model validation

Of 3,563 complete-count test-period targets, 2,384 satisfy the common history criteria across 253 disease-region series. Excluded targets are not zero outcomes. Model outputs, per-target predictions and per-series metrics are in [output/modelling](eda/output/modelling/).

| model | n_predictions | mae_counts_per_country | rmse_log1p | macro_mean_series_rmse_log1p |
| --- | --- | --- | --- | --- |
| log_linear_trend | 2384 | 40.8684 | 0.8707 | 0.7737 |
| seasonal_median_5y | 2384 | 33.3273 | 0.8348 | 0.7551 |
| seasonal_persistence | 2384 | 35.4193 | 0.8763 | 0.7568 |

On common eligible targets, **seasonal_median_5y** has the lowest pooled log-scale RMSE (0.8348). This is a retrospective benchmark result, not evidence of calibrated anomaly thresholds or operational early-warning skill.

## Interpretation and limitations

Reported counts are concentrated in particular diseases/countries and can be driven by extreme entries. Iran's 2011 American foulbrood summaries require source verification. Region totals and growth cannot be interpreted as comparable underlying risk without surveillance and animal-population denominators. Changing disease definitions, subtype aggregation, administrative coverage and reporter composition can create apparent trends. The Both-only policy sensitivity quantifies a material scope decision. Observed 2024 half-year labels with eligible numeric counts are [1, 2]; complete reporting and extraction cutoff remain unverified.

The anomaly screen highlights deviations from a short historical baseline, while validation measures how three reporting-pattern baselines predict later observed values. Neither validates anomaly flags as epidemics. Climate matches 99.36% of observed country-semesters; shared territory/ISO3 mappings require review. Monthly disease seasonality, geospatial risk maps and causal climate effects are not established by these data.

## Validation and reproducibility evidence

The full run passes 16 automated tests before analysis. Tests cover summary priority, regional copies, unknowns versus zeros, synthetic records, conflicts, absent periods, temporal leakage, common evaluation targets and missing-history exclusions. Aggregate totals reconcile across eight independent table grains. Validation predictions are checked to use only earlier training timestamps. Source data are read without mutation. The executed EDA notebook and charts are retained; `python run_pipeline.py` regenerates processing, modelling, validation and this report, and `python eda/execute_notebook.py` refreshes notebook outputs.

## Legacy notebook review

`script.ipynb` and `prepare_climate.py` remain intact as team work. The legacy notebook has regression and climate analyses, but is not the validated submission entry point: it creates synthetic zeros in an early cell, fills absent disease-period reports as zero later, drops all non-Middle-East copies rather than verified identical copies, and defines surge thresholds using the full series before a train/test split. Its in-sample anomaly thresholds, broad biological interpretations and climate/predictive claims are not carried into this report. Re-running it requires additional dependencies listed separately and does not reproduce the audited totals here.

## Next steps most relevant to Challenge 6

Confirm summary policy and subtype additivity; verify large source entries; reconcile renamed disease labels with a documented crosswalk; obtain disease-specific reporting and animal exposure denominators. Then fit overdispersed count models and assess residuals, serial dependence and multiple comparisons. Climate work should use complete semester joins, contiguous lags, country/half-year effects, training-only standardisation and time-ordered validation against strong disease-history baselines. Obtain occurrence dates and publication timestamps before claiming monthly patterns or operational early-warning skill.
