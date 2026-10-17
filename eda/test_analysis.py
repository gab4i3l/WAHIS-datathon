"""Tests for count selection errors that would materially change conclusions."""
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from analysis import load_and_validate, aggregate, build_tables, interpretations


def row(**updates):
    r={'Year':2005,'Semester':'Jan-Jun 2005','World region':'Asia','Country':'Iran',
       'Administrative Division':'A','Disease':'D','Serotype/Subtype/Genotype':'S1',
       'Species':'','Animal Category':'Both animal categories','Outbreak_id':'-',
       'New outbreaks':'4'}
    r.update(updates)
    return r


class SelectionTests(unittest.TestCase):
    def load(self, rows, policy='prefer-both'):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.csv';pd.DataFrame(rows).to_csv(path,index=False)
            return load_and_validate(path,policy)

    def test_region_copy_category_priority_and_subtype(self):
        rows=[row(),row(**{'World region':'Middle East'}),
              row(**{'Animal Category':'Domestic','New outbreaks':'99'}),
              row(**{'Serotype/Subtype/Genotype':'S2','New outbreaks':'3'}),
              row(**{'Species':'Cattle','New outbreaks':'900'})]
        s,a,_,_=self.load(rows)
        self.assertEqual(s['count'].sum(),7)
        self.assertEqual(len(s),2)
        self.assertEqual(a['verified_duplicate_rows_removed'],1)
        self.assertEqual(set(s['World region']),{'Middle East'})

    def test_partial_category_unknown_stays_unknown(self):
        s,_,_,_=self.load([row(**{'Animal Category':'Domestic','New outbreaks':'8'}),
                           row(**{'Animal Category':'Wild','New outbreaks':'-'})])
        self.assertTrue(s['count'].isna().all())
        self.assertTrue(aggregate(s,['Year']).outbreaks.isna().all())

    def test_synthetic_zero_and_orphan_excluded(self):
        s,a,_,o=self.load([row(**{'is_synthetic_summary':True,'New outbreaks':'0'}),
                          row(**{'Species':'Cattle','is_synthetic_summary':False}),
                          row(**{'Country':'Japan','is_synthetic_summary':False,'New outbreaks':'2'})])
        self.assertEqual(s['count'].sum(),2)
        self.assertEqual(a['synthetic_rows_excluded'],1)
        self.assertEqual(len(o),1)

    def test_conflicting_count_quarantines_group(self):
        s,a,c,_=self.load([row(),row(**{'New outbreaks':'6'}),
                          row(**{'Animal Category':'Domestic','New outbreaks':'50'}),
                          row(**{'Country':'Japan','New outbreaks':'2'})])
        self.assertEqual(s['count'].sum(),2)
        self.assertEqual(a['conflicting_summary_keys_excluded'],1)
        self.assertEqual(len(c),2)

    def test_both_only_does_not_infer_absent_both(self):
        s,_,_,_=self.load([row(),row(**{'Country':'Japan','Animal Category':'Domestic','New outbreaks':'10'})],'both-only')
        self.assertEqual(s['count'].sum(),4)

    def test_absent_years_and_insufficient_baseline_stay_unknown(self):
        s,_,_,_=self.load([row()])
        t=build_tables(s)
        self.assertTrue(t['annual'].loc[t['annual'].Year.eq(2006),'outbreaks'].isna().all())
        self.assertEqual(len(t['anomaly_flags']),0)

    def test_report_handles_absent_2024_coverage(self):
        s,a,_,_=self.load([row()],'both-only')
        findings,notes=interpretations(build_tables(s),a)
        self.assertIn('no eligible numeric summary counts', notes['02_semester_trend'][2])
        self.assertEqual(a['observed_semesters_2024'],[])

    def test_fractional_year_rejected(self):
        with self.assertRaises(ValueError):self.load([row(**{'Year':2005.5})])

    def test_unobserved_comparison_window_stays_unknown(self):
        s,_,_,_=self.load([row(**{'Year':2020,'Semester':'Jan-Jun 2020'})])
        change=build_tables(s)['disease_changes'].iloc[0]
        self.assertTrue(pd.isna(change.early_2005_09))
        self.assertTrue(pd.isna(change.fixed_early))
        self.assertTrue(pd.isna(change.change_pct))

    def test_invalid_count_fails(self):
        with self.assertRaises(ValueError):self.load([row(**{'New outbreaks':'-2'})])

    def test_actual_zero_is_distinct_from_unknown(self):
        s,_,_,_=self.load([row(**{'New outbreaks':'0'}),row(**{'Country':'Japan','New outbreaks':'-'})])
        g=aggregate(s,['Country']).set_index('Country')
        self.assertEqual(g.loc['Iran','outbreaks'],0)
        self.assertTrue(pd.isna(g.loc['Japan','outbreaks']))

if __name__=='__main__':unittest.main()
