"""Expanding-window validation of interpretable disease-region reporting baselines.

The outcome is reported new outbreaks / countries with numeric disease summaries,
not population incidence. Each test target is predicted using earlier semesters only.
"""
from pathlib import Path
import numpy as np
import pandas as pd

MODELS = ['seasonal_persistence', 'seasonal_median_5y', 'log_linear_trend']
PREDICTION_COLUMNS = ['Disease', 'World region', 'Year', 'half', 'model', 'observed',
                      'predicted', 'training_last_year', 'training_last_half', 'training_n',
                      'test_countries']


def design(frame):
    return np.column_stack([np.ones(len(frame)), (frame.Year - 2005) + (frame.half - 1)/2,
                            frame.half - 1])


def backtest(table, test_start=2019, test_end=2024, min_train=20):
    """Predict rates on common eligible targets, never fill missing reports with zero.

    Eligibility: known counts, no unknown constituent groups, positive reporting
    denominator, >=20 earlier observed semesters, all five immediately preceding
    same-half years. Model parameters and eligibility at time t use only history <t.
    Test outcomes become available to subsequent expanding-window origins.
    """
    needed = ['Disease','World region','Year','half','outbreaks','unknown_groups','countries_with_known_counts']
    missing = set(needed)-set(table)
    if missing:
        raise ValueError(f'Missing modelling columns: {sorted(missing)}')
    x = table[needed].copy()
    if x.duplicated(['Disease','World region','Year','half']).any():
        raise ValueError('Duplicate disease-region-semester keys')
    valid = x.outbreaks.notna() & x.unknown_groups.eq(0) & x.countries_with_known_counts.gt(0)
    x = x[valid].copy()
    x['rate'] = x.outbreaks / x.countries_with_known_counts
    if not np.isfinite(x.rate).all() or x.rate.lt(0).any():
        raise ValueError('Modelling rates must be finite and nonnegative')
    x['time'] = x.Year*2 + x.half
    rows=[]
    eligible_targets = int(x.Year.between(test_start,test_end).sum())
    for (d,r),g in x.groupby(['Disease','World region'], observed=True):
        g=g.sort_values('time')
        for _,cur in g[g.Year.between(test_start,test_end)].iterrows():
            past=g[g.time.lt(cur.time)]
            seasonal=past[past.half.eq(cur.half)&past.Year.between(cur.Year-5,cur.Year-1)].sort_values('Year')
            if len(past)<min_train or len(seasonal)!=5:
                continue
            beta,_,rank,_=np.linalg.lstsq(design(past),np.log1p(past.rate),rcond=None)
            if rank!=3:
                continue
            forecast=float(np.expm1((design(cur.to_frame().T) @ beta).item()))
            if not np.isfinite(forecast):
                raise ValueError('Nonfinite model prediction')
            predictions=[float(seasonal.iloc[-1].rate),float(seasonal.rate.median()),max(0.,forecast)]
            last=past.iloc[-1]
            for model,pred in zip(MODELS,predictions):
                rows.append({'Disease':d,'World region':r,'Year':int(cur.Year),'half':int(cur.half),
                             'model':model,'observed':float(cur.rate),'predicted':pred,
                             'training_last_year':int(last.Year),'training_last_half':int(last.half),
                             'training_n':len(past),'test_countries':int(cur.countries_with_known_counts)})
    pred=pd.DataFrame(rows,columns=PREDICTION_COLUMNS)
    metrics=[];by_series=[]
    def score(g):
        error=g.predicted-g.observed
        return {'n_predictions':len(g),'mae_counts_per_country':float(error.abs().mean()),
                'rmse_log1p':float(np.sqrt(np.square(np.log1p(g.predicted)-np.log1p(g.observed)).mean()))}
    for model,g in pred.groupby('model',observed=True):
        metrics.append({'model':model,**score(g)})
    for (d,r,m),g in pred.groupby(['Disease','World region','model'],observed=True):
        by_series.append({'Disease':d,'World region':r,'model':m,**score(g)})
    metrics=pd.DataFrame(metrics,columns=['model','n_predictions','mae_counts_per_country','rmse_log1p'])
    series=pd.DataFrame(by_series,columns=['Disease','World region','model','n_predictions','mae_counts_per_country','rmse_log1p'])
    if len(metrics):
        macro=series.groupby('model').rmse_log1p.mean()
        metrics['macro_mean_series_rmse_log1p']=metrics.model.map(macro)
    metadata={'test_start':test_start,'test_end':test_end,'minimum_training_semesters':min_train,
              'available_complete_test_targets':eligible_targets,
              'scored_common_targets':len(pred)//len(MODELS),
              'scored_series':len(pred[['Disease','World region']].drop_duplicates()),
              'protocol':'Expanding window; one semester ahead; same eligible targets for all models.',
              'outcome':'Known reported new outbreaks / countries with numeric disease summaries.',
              'limitations':'Reporting-period availability is assumed; publication timestamps and stable surveillance denominators are unavailable. Performance is conditional on observed records, not operational early-warning validity.'}
    return pred,metrics,series,metadata


def save_validation(table, output):
    import json
    pred,metrics,series,metadata=backtest(table)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    pred.to_csv(out/'predictions.csv',index=False)
    metrics.to_csv(out/'metrics.csv',index=False)
    series.to_csv(out/'metrics_by_series.csv',index=False)
    (out/'validation.json').write_text(json.dumps(metadata,indent=2))
    return pred,metrics,series,metadata
