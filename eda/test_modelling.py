"""Verify time ordering and missing-data behaviour, not regression implementation."""
import unittest
import numpy as np
import pandas as pd
from modelling import backtest, MODELS


def example():
    return pd.DataFrame([{'Disease':'D','World region':'R','Year':y,'half':h,
        'outbreaks':2*(y-2000)+h, 'unknown_groups':0,'countries_with_known_counts':2}
        for y in range(2005,2025) for h in [1,2]])


class ValidationTests(unittest.TestCase):
    def test_only_history_affects_prediction(self):
        x=example();a,_,_,_=backtest(x)
        # Change the target and every subsequent outcome; the first prediction must be unchanged.
        x.loc[x.Year.ge(2019),'outbreaks']=1000000
        b,_,_,_=backtest(x)
        first=a[a.Year.eq(2019)&a.half.eq(1)].set_index('model').predicted
        changed=b[b.Year.eq(2019)&b.half.eq(1)].set_index('model').predicted
        np.testing.assert_allclose(first,changed)
        self.assertTrue((a.training_last_year*2+a.training_last_half < a.Year*2+a.half).all())

    def test_missing_season_is_not_treated_as_zero(self):
        x=example();x.loc[x.Year.eq(2018)&x.half.eq(1),'outbreaks']=np.nan
        p,_,_,_=backtest(x)
        self.assertFalse((p.Year.eq(2019)&p.half.eq(1)).any())
        self.assertTrue((p.Year.eq(2019)&p.half.eq(2)).any())

    def test_models_share_targets_and_metrics_are_finite(self):
        p,m,s,meta=backtest(example())
        self.assertEqual(set(m.model),set(MODELS))
        self.assertTrue(p.groupby(['Year','half']).model.nunique().eq(3).all())
        self.assertEqual(meta['scored_common_targets'],12)
        self.assertTrue(np.isfinite(m.select_dtypes('number')).all().all())
        self.assertTrue(p.predicted.ge(0).all())

    def test_unknown_target_and_zero_denominator_are_excluded(self):
        x=example();x.loc[x.Year.eq(2024),'unknown_groups']=1
        x.loc[x.Year.eq(2023),'countries_with_known_counts']=0
        p,_,_,_=backtest(x)
        self.assertFalse(p.Year.ge(2023).any())

    def test_insufficient_history_yields_documented_empty_output(self):
        p,m,s,meta=backtest(example().query('Year >= 2020'))
        self.assertTrue(p.empty and m.empty and s.empty)
        self.assertEqual(meta['scored_common_targets'],0)

if __name__=='__main__':unittest.main()
