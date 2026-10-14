"""Audited Part 3 EDA. Run from any directory; never modifies upstream files."""
from pathlib import Path
import argparse
import hashlib
import json
import os
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/wahis-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, StrMethodFormatter
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
KEY = ['Year', 'Semester', 'World region', 'Country', 'Administrative Division', 'Disease', 'Serotype/Subtype/Genotype']
REQUIRED = KEY + ['Species', 'Animal Category', 'Outbreak_id', 'New outbreaks']
SENTINELS = ['', '-', 'NA', 'N/A']


def aggregate(frame, keys):
    """Known counts only; all-unknown and absent cells stay unknown."""
    g = frame.groupby(keys, dropna=False, observed=True)
    a = g['count'].sum(min_count=1).rename('outbreaks').to_frame()
    a['summary_groups'] = g.size()
    a['unknown_groups'] = g['count'].apply(lambda x: x.isna().sum())
    a['countries_with_known_counts'] = frame[frame['count'].notna()].groupby(keys, observed=True, dropna=False)['Country'].nunique()
    return a.reset_index()


def load_and_validate(path, policy='prefer-both'):
    raw = pd.read_csv(path, low_memory=False)
    missing = sorted(set(REQUIRED) - set(raw))
    if missing:
        raise ValueError(f'Missing columns: {missing}. Export summary rows with original columns and synthetic flag.')
    audit = {'input': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'input_rows': len(raw), 'policy': policy}
    x = raw.copy()
    for c in REQUIRED:
        if c != 'Year':
            x[c] = x[c].astype('string').str.strip().replace(SENTINELS, pd.NA)
    year = pd.to_numeric(x['Year'], errors='coerce')
    audit['out_of_scope_or_invalid_year_rows'] = int((~year.between(2005, 2024)).sum())
    x = x[year.between(2005, 2024)].copy()
    x['Year'] = year.loc[x.index].astype(int)
    if 'is_synthetic_summary' in x:
        flag = x['is_synthetic_summary'].astype('string').str.lower()
        if not flag.fillna('false').isin(['true','false','1','0']).all():
            raise ValueError('Unrecognised is_synthetic_summary flag')
        synthetic = flag.isin(['true', '1'])
        audit['synthetic_rows_excluded'] = int(synthetic.sum())
        x = x[~synthetic].copy()
    else:
        audit['synthetic_rows_excluded'] = 0
    if x[['Country','Disease','World region','Semester','Animal Category']].isna().any().any():
        raise ValueError('Missing required geography/disease/semester/category labels: resolve upstream.')
    parsed = x['Semester'].str.extract(r'^(Jan-Jun|Jul-Dec) (\d{4})$')
    if parsed.isna().any().any() or not pd.to_numeric(parsed[1]).eq(x.Year).all():
        raise ValueError('Semester labels must match Year and use Jan-Jun YYYY or Jul-Dec YYYY.')
    x['half'] = parsed[0].map({'Jan-Jun': 1, 'Jul-Dec': 2}).astype(int)
    # Verify duplicates after choosing disjoint regions; retain nonduplicated records.
    me = set(x.loc[x['World region'].eq('Middle East'), 'Country'])
    audit['countries_reassigned_to_middle_east'] = sorted(me)
    x.loc[x.Country.isin(me), 'World region'] = 'Middle East'
    audit['verified_duplicate_rows_removed'] = int(x.duplicated().sum())
    x = x.drop_duplicates()
    if x.groupby('Country')['World region'].nunique().gt(1).any():
        raise ValueError('Unresolved overlapping regions outside the documented Middle East overlap.')
    audit['outbreak_id_rows_excluded'] = int(x.Outbreak_id.notna().sum())
    smr = x[x.Outbreak_id.isna() & x.Species.isna()].copy()
    audit['candidate_summary_rows'] = len(smr)
    smr['count'] = pd.to_numeric(smr['New outbreaks'], errors='coerce').astype('float64')
    invalid = smr['New outbreaks'].notna() & smr['count'].isna()
    if invalid.any() or (smr['count'].dropna() < 0).any() or (smr['count'].dropna() % 1 != 0).any():
        raise ValueError('Summary outbreak counts must be nonnegative integers or explicit missing sentinels.')
    audit['missing_numeric_summary_rows'] = int(smr['count'].isna().sum())
    if not smr['Animal Category'].isin(['Both animal categories','Domestic','Wild']).all():
        raise ValueError('Unsupported animal category; confirm selection contract upstream.')
    identity = KEY + ['Animal Category']
    # Same key/count can differ in ancillary fields; identical count retained once.
    dedup = smr.drop_duplicates(identity + ['count'])
    conflict_mask = dedup.duplicated(identity, keep=False)
    conflicts = dedup[conflict_mask].copy()
    conflict_keys = conflicts[identity].drop_duplicates()
    audit['conflicting_summary_keys_excluded'] = len(conflict_keys)
    audit['same_key_same_count_rows_removed'] = len(smr) - len(dedup)
    smr = dedup[~conflict_mask].copy()
    # Quarantine whole subtype group if any category has a conflicting count.
    bad_groups = conflicts[KEY].drop_duplicates()
    if len(bad_groups):
        smr = smr.merge(bad_groups.assign(bad=True), on=KEY, how='left')
        smr = smr[smr.bad.isna()].drop(columns='bad')
    both = smr[smr['Animal Category'].eq('Both animal categories')].copy()
    cat = smr[~smr['Animal Category'].eq('Both animal categories')].copy()
    cat = cat.merge(both[KEY].assign(has_both=True), on=KEY, how='left')
    cat = cat[cat.has_both.isna()].drop(columns='has_both')
    fallback = cat.groupby(KEY, dropna=False, observed=True).agg(
        count=('count', lambda s: s.sum(min_count=len(s))), half=('half','first')).reset_index()
    fallback['source'] = 'category fallback'
    both = both[KEY + ['count','half']].assign(source='Both animal categories')
    summaries = pd.concat([both, fallback], ignore_index=True) if policy == 'prefer-both' else both
    if summaries.duplicated(KEY).any():
        raise AssertionError('Summary grain is not unique')
    details = x[x.Outbreak_id.isna() & x.Species.notna()]
    orphan = details[KEY].drop_duplicates().merge(pd.concat([both[KEY],fallback[KEY]]).drop_duplicates().assign(found=True), on=KEY, how='left')
    audit.update({'selected_summary_groups':len(summaries), 'category_fallback_groups':len(fallback),
                  'both_only_known_outbreaks':float(both['count'].sum()),
                  'category_fallback_known_outbreaks':float(fallback['count'].sum()),
                  'selected_unknown_groups':int(summaries['count'].isna().sum()),
                  'detail_groups_without_summary':int(orphan.found.isna().sum()),
                  'selected_known_outbreaks':float(summaries['count'].sum()),
                  'diseases':int(summaries.Disease.nunique()), 'countries':int(summaries.Country.nunique()),
                  'regions':sorted(summaries['World region'].unique().tolist())})
    return summaries, audit, conflicts, orphan[orphan.found.isna()].drop(columns='found')


def build_tables(s):
    t = {}
    for name,keys in {'annual':['Year'], 'semester':['Year','half'], 'region':['World region'],
                      'country':['Country','World region'], 'disease':['Disease'],
                      'disease_year':['Disease','Year'], 'region_year':['World region','Year'],
                      'disease_region':['Disease','World region'],
                      'disease_region_semester':['Disease','World region','Year','half'],
                      'disease_half':['Disease','half'], 'country_disease_year':['Country','Disease','Year']}.items():
        t[name] = aggregate(s,keys)
    t['annual'] = t['annual'].set_index('Year').reindex(range(2005,2025)).reset_index()
    grid = pd.MultiIndex.from_product([range(2005,2025), [1,2]], names=['Year','half'])
    t['semester'] = t['semester'].set_index(['Year','half']).reindex(grid).reset_index()
    t['annual']['yoy_pct'] = t['annual'].outbreaks.pct_change(fill_method=None) * 100
    # Disease-specific countries with observed numeric summaries, not all-country disease-zero imputation.
    panel = s[s['count'].notna()].groupby(['Disease','Country','Year'], observed=True)['count'].sum().reset_index()
    years = set(range(2005,2010)) | set(range(2020,2025))
    rows=[]
    for disease,g in panel.groupby('Disease', observed=True):
        early=g[g.Year.between(2005,2009)]['count'].sum();late=g[g.Year.between(2020,2024)]['count'].sum()
        observed = g[g.Year.isin(years)].groupby('Country').Year.nunique()
        fixed=set(observed[observed.eq(10)].index)
        f=g[g.Country.isin(fixed)]
        e=f[f.Year.between(2005,2009)]['count'].sum();l=f[f.Year.between(2020,2024)]['count'].sum()
        rows.append({'Disease':disease,'early_2005_09':early,'late_2020_24':late,
                     'change_pct':(late/early-1)*100 if early>0 else np.nan,
                     'fixed_countries':len(fixed),'fixed_early':e,'fixed_late':l,
                     'fixed_change_pct':(l/e-1)*100 if e>0 else np.nan})
    t['disease_changes']=pd.DataFrame(rows)
    # Prospective descriptive baseline: previous five years of the same half only.
    dr=t['disease_region_semester'].copy()
    dr['known_per_country']=dr.outbreaks / dr.countries_with_known_counts
    rows=[]
    for (d,r),g in dr.groupby(['Disease','World region'], observed=True):
        for _,cur in g.iterrows():
            past=g[g.half.eq(cur.half) & g.Year.between(cur.Year-5,cur.Year-1) & g.unknown_groups.eq(0)].dropna(subset=['known_per_country'])
            if len(past)!=5 or cur.unknown_groups or pd.isna(cur.known_per_country):continue
            v=np.log1p(past.known_per_country.to_numpy());median=np.median(v);mad=np.median(np.abs(v-median))
            if mad<=1e-10:continue
            score=(np.log1p(cur.known_per_country)-median)/(1.4826*mad)
            base=np.expm1(median)
            rows.append({'Disease':d,'World region':r,'Year':int(cur.Year),'half':int(cur.half),
                         'outbreaks':cur.outbreaks,'countries':cur.countries_with_known_counts,
                         'baseline_per_country':base,'observed_per_country':cur.known_per_country,
                         'robust_score':score,'exploratory_flag':bool(score>3.5),
                         'baseline_countries_min':past.countries_with_known_counts.min(),
                         'baseline_countries_max':past.countries_with_known_counts.max()})
    t['anomaly_scores']=pd.DataFrame(rows,columns=['Disease','World region','Year','half','outbreaks','countries','baseline_per_country','observed_per_country','robust_score','exploratory_flag','baseline_countries_min','baseline_countries_max'])
    tc=s.groupby(['Disease','World region','Year','half','Country'],observed=True,dropna=False)['count'].sum(min_count=1).reset_index().sort_values('count',ascending=False)
    tc=tc.drop_duplicates(['Disease','World region','Year','half']).rename(columns={'Country':'largest_contributing_country','count':'largest_country_known_counts'})
    if len(t['anomaly_scores']):
        t['anomaly_scores']=t['anomaly_scores'].merge(tc,on=['Disease','World region','Year','half'],how='left',validate='one_to_one')
    else:
        t['anomaly_scores']['largest_contributing_country']=pd.Series(dtype='string')
        t['anomaly_scores']['largest_country_known_counts']=pd.Series(dtype='float64')
    t['anomaly_scores']['fold_vs_baseline']=t['anomaly_scores'].observed_per_country / t['anomaly_scores'].baseline_per_country.replace(0,np.nan)
    t['anomaly_flags']=t['anomaly_scores'].loc[lambda d:d.exploratory_flag.eq(True)].sort_values('robust_score',ascending=False)
    return t


PRIORITY = ['African swine fever virus (Inf. with)', 'Foot and mouth disease virus (Inf. with)',
            'Lumpy skin disease virus (Inf. with)', 'Bluetongue virus (Inf. with)',
            'High pathogenicity avian influenza viruses (Inf. with) (poultry)',
            'Influenza A viruses of high pathogenicity (Inf. with) (non-poultry including wild birds) (2017-)']


def short(d):
    return d.replace('High pathogenicity avian influenza viruses (Inf. with) (poultry)', 'HPAI (poultry)').replace('Influenza A viruses of high pathogenicity (Inf. with) (non-poultry including wild birds) (2017-)', 'HPAI (non-poultry, 2017–)').replace(' virus (Inf. with)','').replace(' (Inf. with)','').replace(' (Inf. of honey bees with)','').replace('Serotype/Subtype/Genotype','Subtype')


def chart(fig, name, output):
    fig.tight_layout(rect=(0,.045,1,.97) if name=='12_priority_disease_regions' else (0,0,1,1))
    for extension in ['png','svg']:
        fig.savefig(output/'charts'/f'{name}.{extension}',dpi=300,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def make_charts(s,t,out):
    sns.set_theme(style='whitegrid',palette='colorblind',font_scale=0.95)
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    region_colors=dict(zip(sorted(s['World region'].unique()),sns.color_palette('colorblind',s['World region'].nunique())))
    a=t['annual']; top=t['disease'].nlargest(10,'outbreaks').Disease.tolist()
    fig,ax=plt.subplots(3,1,figsize=(11,9),sharex=True)
    ax[0].plot(a.Year,a.outbreaks,marker='o');ax[0].set(title='Known reported new outbreaks, 2005–2024',ylabel='New outbreaks')
    ax[0].yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    ax[1].bar(a.Year,a.yoy_pct);ax[1].axhline(0,color='black',lw=.7);ax[1].set(ylabel='Year-on-year change (%)')
    ax[2].plot(a.Year,a.countries_with_known_counts,marker='o',color='#D55E00');ax[2].set(ylabel='Countries with numeric summaries',xlabel='Year');ax[2].xaxis.set_major_locator(MaxNLocator(integer=True))
    chart(fig,'01_annual_trend_coverage',out)
    se=t['semester'];fig,ax=plt.subplots(figsize=(11,4));ax.plot(se.Year+(se.half-1)*.5,se.outbreaks,marker='.',label='Known counts')
    roll=se.outbreaks.rolling(4,min_periods=4).mean()
    ax.plot(se.Year+(se.half-1)*.5,roll.to_numpy(),label='Four observed semesters: trailing mean',lw=2.5)
    ax.set(title='Six-monthly reported outbreak counts',xlabel='Year (half-year positions)',ylabel='New outbreaks');ax.legend();chart(fig,'02_semester_trend',out)
    fig,axes=plt.subplots(5,2,figsize=(14,16),sharex=True)
    for ax,d in zip(axes.flat,top):
        g=t['disease_year'].query('Disease == @d').set_index('Year').reindex(range(2005,2025))
        ax.plot(g.index,g.outbreaks,marker='.',color='#0072B2');ax.set_title(short(d),fontsize=10);ax.set_ylabel('New outbreaks');ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
    for ax in list(axes.flat)[len(top):]:ax.set_visible(False)
    chart(fig,'03_top_disease_trends',out)
    fig,axes=plt.subplots(1,2,figsize=(16,6),gridspec_kw={'width_ratios':[1.8,1]})
    d=t['disease'].nlargest(10,'outbreaks').sort_values('outbreaks');axes[0].barh([short(v) for v in d.Disease],d.outbreaks,color='#0072B2');axes[0].set(title='Top 10 disease labels',xlabel='Known new outbreaks')
    r=t['region'].sort_values('outbreaks');axes[1].barh(r['World region'],r.outbreaks,color='#009E73');axes[1].set(title='Disjoint regional totals',xlabel='Known new outbreaks');chart(fig,'04_disease_region_ranking',out)
    fig,ax=plt.subplots(figsize=(11,5))
    for r,g in t['region_year'].groupby('World region', observed=True):
        g=g.set_index('Year').reindex(range(2005,2025));ax.plot(g.index,g.outbreaks,label=r,color=region_colors[r])
    ax.set(title='Regional reported outbreak trends',xlabel='Year',ylabel='Known new outbreaks');ax.legend(ncol=4,fontsize=8);ax.xaxis.set_major_locator(MaxNLocator(integer=True));chart(fig,'05_region_trends',out)
    dr=t['disease_region'].pivot(index='Disease',columns='World region',values='outbreaks').reindex(top)
    fig,ax=plt.subplots(figsize=(13,7));sns.heatmap(np.log10(dr+1),mask=dr.isna(),cmap='Blues',ax=ax,cbar_kws={'label':'log10(known outbreaks + 1)'},yticklabels=[short(v) for v in dr.index]);ax.set(title='Top diseases × region; blank = no observed summary',xlabel='Region',ylabel='');chart(fig,'06_disease_region_heatmap',out)
    # Missing disease-region combinations remain unobserved; composition uses observed contributions only.
    all_dr=t['disease_region'].pivot(index='World region',columns='Disease',values='outbreaks')
    composition=all_dr[top].copy();composition['Other observed diseases']=all_dr.drop(columns=top).sum(axis=1,min_count=1)
    comp=composition.div(all_dr.sum(axis=1,min_count=1),axis=0)
    fig,ax=plt.subplots(figsize=(13,7));bottom=np.zeros(len(comp))
    composition_colors = dict(zip(top,sns.color_palette('tab20',10)))
    composition_colors['Other observed diseases']='#777777'
    for d in comp:
        heights=comp[d].to_numpy(); ax.bar(comp.index,heights,bottom=bottom,label=short(d),color=composition_colors[d]);bottom+=np.nan_to_num(heights)
    ax.set(title='Composition of known regional counts',ylabel='Share of known new outbreaks',xlabel='Region');ax.legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=8);chart(fig,'07_region_composition',out)
    dy=t['disease_year'].pivot(index='Disease',columns='Year',values='outbreaks').reindex(top,columns=range(2005,2025))
    fig,ax=plt.subplots(figsize=(15,6));sns.heatmap(np.log10(dy+1),mask=dy.isna(),cmap='Blues',ax=ax,yticklabels=[short(v) for v in dy.index],cbar_kws={'label':'log10(known outbreaks + 1)'});ax.set(title='Top diseases × year; blank = no observed summary',ylabel='');chart(fig,'08_disease_year_heatmap',out)
    sh=t['disease_half'].pivot(index='Disease',columns='half',values='outbreaks').reindex(top)
    sh=sh.div(sh.sum(axis=1,min_count=1),axis=0)
    fig,axes=plt.subplots(1,2,figsize=(15,6),gridspec_kw={'width_ratios':[1,1.6]})
    sns.heatmap(sh,mask=sh.isna(),annot=True,fmt='.0%',cmap='Blues',ax=axes[0],xticklabels=['Jan–Jun','Jul–Dec'],yticklabels=[short(v) for v in sh.index],cbar=False);axes[0].set(title='Half-year shares across 2005–2024',xlabel='Half-year',ylabel='')
    hy=t['semester'].pivot(index='half',columns='Year',values='outbreaks');sns.heatmap(np.log10(hy+1),mask=hy.isna(),ax=axes[1],cmap='Blues',yticklabels=['Jan–Jun','Jul–Dec'],cbar_kws={'label':'log10(known outbreaks + 1)'});axes[1].set(title='Semester × year counts',ylabel='',xlabel='Year');chart(fig,'09_half_year_patterns',out)
    flags=t['anomaly_flags']
    candidates=flags[flags.Disease.isin(PRIORITY)&flags.countries.ge(3)&flags.outbreaks.ge(50)]
    if not len(candidates): candidates=flags
    choices=candidates.drop_duplicates('Disease')[['Disease','World region']].head(4)
    if len(choices):
        fig,axes=plt.subplots(len(choices),1,figsize=(12,3.2*len(choices)),squeeze=False)
        for ax,(_,c) in zip(axes.flat,choices.iterrows()):
            g=t['disease_region_semester'];g=g[g.Disease.eq(c.Disease)&g['World region'].eq(c['World region'])].sort_values(['Year','half']);x=g.Year+(g.half-1)*.5
            ax.plot(x,g.outbreaks/g.countries_with_known_counts,label='Known counts / countries with numeric summaries')
            b=t['anomaly_scores'];b=b[b.Disease.eq(c.Disease)&b['World region'].eq(c['World region'])].sort_values(['Year','half']);xx=b.Year+(b.half-1)*.5
            ax.plot(xx,b.baseline_per_country,ls='--',label='Prior five same-half years: median')
            f=b[b.exploratory_flag];ax.scatter(f.Year+(f.half-1)*.5,f.observed_per_country,color='#D55E00',label='Exploratory score > 3.5',zorder=3)
            ax.set(title=f'{short(c.Disease)} — {c["World region"]}',ylabel='Counts per observed country',xlabel='Year');ax.legend(fontsize=7)
        chart(fig,'10_exploratory_anomalies',out)
    co=t['country'].nlargest(15,'outbreaks').sort_values('outbreaks');fig,ax=plt.subplots(figsize=(10,6));ax.barh(co.Country,co.outbreaks,color='#009E73');ax.set(title='Top 15 countries by known reported new outbreaks',xlabel='New outbreaks');chart(fig,'11_country_ranking',out)


    available=[d for d in PRIORITY if d in set(s.Disease)]
    if available:
        fig,axes=plt.subplots(3,2,figsize=(14,12),sharex=True)
        for ax,d in zip(axes.flat,available):
            for r,g in t['disease_region_semester'].loc[lambda v:v.Disease.eq(d)].groupby('World region', observed=True):
                annual=g.groupby('Year').outbreaks.sum(min_count=1).reindex(range(2005,2025))
                ax.plot(annual.index,annual.values,label=r,color=region_colors[r])
            ax.set(title=short(d),ylabel='Known new outbreaks',xlabel='Year');ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
        for ax in list(axes.flat)[len(available):]:ax.set_visible(False)
        from matplotlib.lines import Line2D
        fig.legend(handles=[Line2D([0],[0],color=c,label=r) for r,c in region_colors.items()],loc='lower center',ncol=6,fontsize=9)
        fig.tight_layout(rect=(0,.045,1,.97))
        fig.suptitle('Selected diseases: regional annual trends',fontsize=15)
        chart(fig,'12_priority_disease_regions',out)


def climate_audit(s,root):
    cp=root/'data/climate_country_month.csv';ip=root/'data/wahis_country_iso3.csv'
    if not cp.exists() or not ip.exists():return {'status':'Climate or country mapping missing; join skipped.'},pd.DataFrame()
    c=pd.read_csv(cp);iso=pd.read_csv(ip)
    if iso.Country.duplicated().any() or c.duplicated(['iso3','year','month']).any():raise ValueError('Climate mapping or monthly climate keys are not unique.')
    c=c[c.year.between(2005,2024)].copy();c['half']=np.where(c.month.le(6),1,2)
    cs=c.groupby(['iso3','year','half']).agg(months=('month','nunique'),prec=('prec',lambda v:v.sum(min_count=6)),tmin=('tmin',lambda v:v.mean() if v.notna().sum()==6 else np.nan),tmax=('tmax',lambda v:v.mean() if v.notna().sum()==6 else np.nan)).reset_index()
    cs=cs[cs.months.eq(6)]
    panel=s[['Country','Year','half']].drop_duplicates().merge(iso,on='Country',how='left',validate='many_to_one').merge(cs,left_on=['iso3','Year','half'],right_on=['iso3','year','half'],how='left',validate='many_to_one')
    matched=panel[['prec','tmin','tmax']].notna().all(axis=1)
    return {'status':'Audited join only; no association or predictive claims.', 'observed_country_semesters':len(panel), 'complete_climate_matches':int(matched.sum()),'match_pct':float(matched.mean()*100),'unmatched_countries':sorted(panel.loc[~matched,'Country'].unique().tolist()),'shared_iso3_codes':iso[iso.iso3.duplicated(keep=False)].to_dict('records')},panel


def interpretations(t,audit):
    a=t['annual'];peak=a.loc[a.outbreaks.idxmax()];d=t['disease'].sort_values('outbreaks',ascending=False);r=t['region'].sort_values('outbreaks',ascending=False);co=t['country'].sort_values('outbreaks',ascending=False);flags=t['anomaly_flags']
    total=a.outbreaks.sum();driver=t['country_disease_year'].loc[lambda v:v.Year.eq(int(peak.Year))].sort_values('outbreaks',ascending=False).iloc[0]
    bt=t['disease_half'].loc[lambda v:v.Disease.eq('Bluetongue virus (Inf. with)')]
    bt_share=bt.loc[bt.half.eq(2),'outbreaks'].sum()/bt.outbreaks.sum() if bt.outbreaks.sum()>0 else np.nan
    changes=t['disease_changes'];eligible=changes[changes.fixed_countries.ge(5)&changes.fixed_early.ge(100)]
    rising=eligible.sort_values('fixed_change_pct',ascending=False).iloc[0] if len(eligible) else None
    falling=eligible.sort_values('fixed_change_pct').iloc[0] if len(eligible) else None
    findings=[f'The largest country-disease contribution in the peak year is {driver.Country}: {short(driver.Disease)}, {driver.outbreaks:,.0f} ({driver.outbreaks/peak.outbreaks:.1%} of {int(peak.Year)} known counts). This source entry needs verification before an epidemiological explanation.',
              f'The highest annual known count is {int(peak.Year)} ({peak.outbreaks:,.0f}); this is a reported-count peak, not an incidence estimate.',
              f'{short(d.iloc[0].Disease)} leads the disease ranking ({d.iloc[0].outbreaks:,.0f}); the top ten labels contribute {d.head(10).outbreaks.sum()/total:.1%} of known counts.',
              f'{r.iloc[0]["World region"]} contributes the largest regional share ({r.iloc[0].outbreaks/total:.1%}); regions are disjoint after verified duplicate removal.',
              f'{co.iloc[0].Country} has the highest known country count ({co.iloc[0].outbreaks:,.0f}); the top five countries contribute {co.head(5).outbreaks.sum()/total:.1%}.',
              f'Countries with numeric summary counts vary from {int(a.countries_with_known_counts.min())} to {int(a.countries_with_known_counts.max())} annually; coverage limits trend interpretation.',
              f'Category fallback adds {audit["category_fallback_known_outbreaks"]:,.0f} known counts beyond Both-only summaries ({audit["both_only_known_outbreaks"]:,.0f}); this sensitivity materially affects scope.',
              f'The trailing same-half log-MAD screen flags {len(flags)} of {len(t["anomaly_scores"])} eligible disease-region-semesters; these are candidates for review, not validated significant changes.']
    findings.append(f'Bluetongue has {bt_share:.1%} of known counts in Jul–Dec; this is pooled half-year reporting asymmetry, not confirmed monthly onset seasonality.')
    asf=changes.loc[changes.Disease.eq('African swine fever virus (Inf. with)')]
    if len(asf):
        v=asf.iloc[0]
        findings.append(f'ASF known totals increase from {v.early_2005_09:,.0f} in 2005–09 to {v.late_2020_24:,.0f} in 2020–24 ({v.change_pct:+,.1f}%). Only {int(v.fixed_countries)} country has numeric summaries in every comparison year: changing participation prevents a broad fixed-country trend claim.')
    se=t['semester'];last=se[se.Year.eq(2024)]
    notes={
      '01_annual_trend_coverage':('How do reported counts and coverage change annually?', 'Sum known selected New outbreaks by Year; percentage change uses consecutive observed years without filling missing counts.', f'{int(peak.Year)} peaks at {peak.outbreaks:,.0f}; {driver.Country} / {short(driver.Disease)} contributes {driver.outbreaks/peak.outbreaks:.1%} of that total.', 'Use the peak and coverage changes to choose periods for disease-specific review.', 'Unknown groups contribute no numeric count; counts may be partial. Country numbers do not measure complete reporting or livestock exposure.'),
      '02_semester_trend':('When do six-month reported counts peak?', 'Sum by explicit reporting semester; add a trailing mean of four observed semesters.',f'2024 contains {len(last)} semester labels; country coverage is '+', '.join(f'half {int(v.half)}: {int(v.countries_with_known_counts)}' for _,v in last.iterrows())+'.','Half-year variation can guide finer data requests.','These are reporting-period counts; precise onset/report dates and monthly seasonality are unavailable. A trailing mean is descriptive.'),
      '03_top_disease_trends':('Are high-count diseases stable or dominated by spikes?', 'Use unmerged top ten source labels and separate annual y-axis scales; missing years remain gaps.', f'The top ten labels account for {d.head(10).outbreaks.sum()/total:.1%} of known counts. See exported series for exact peaks.', 'Separate scales reveal shapes obscured by the global total.', 'Disease definitions change over time; no merged HPAI or tuberculosis continuity is assumed. Counts across disease definitions may not represent unique biological events.'),
      '04_disease_region_ranking':('Which diseases and regions contribute most known counts?', 'Sum known counts after verified duplication removal, subtype-preserving selection and category priority.',f'{short(d.iloc[0].Disease)} and {r.iloc[0]["World region"]} lead their rankings.','Prioritise these contributors for source verification and targeted analysis.','Reported counts reflect reporting and heterogeneous outbreak definitions, not underlying risk; bee animal units must not be confused with outbreak counts.'),
      '05_region_trends':('Do regions show different temporal patterns?', 'Annual regional sums with missing region-years left as gaps.',f'The largest cumulative regional share is {r.iloc[0]["World region"]} ({r.iloc[0].outbreaks/total:.1%}).','Review regional peaks separately rather than infer a single global trajectory.','Country participation and administrative coverage vary; regional totals lack population denominators.'),
      '06_disease_region_heatmap':('Which top diseases dominate where?', 'Known disease-region counts on log10(count+1); blanks are unobserved, explicit zero remains zero.',f'{short(d.iloc[0].Disease)} is the highest-count source disease label overall.','Log colour supports comparison across large differences in scale.','Colour does not indicate adjusted risk or establish disease absence in blank cells.'),
      '07_region_composition':('How does the disease mix differ across regions?', 'Shares of each regional known-count total: top ten labels plus all other observed disease labels.',f'Top ten labels contribute {d.head(10).outbreaks.sum()/total:.1%} globally; regional mixes are in disease_region.csv.','Composition is useful for choosing regional disease case studies.','Shares condition on known counts. Blank combinations add no observed contribution; this does not impute disease absence.'),
      '08_disease_year_heatmap':('Which high-count diseases have abrupt peaks or changing label coverage?', 'Log10 annual sums for unchanged top source labels, with gaps retained.',f'The global count peak is {int(peak.Year)}; each disease may peak in a different year.','Compare concentrated spikes with sustained patterns before selecting a model.','Renamed or newly introduced labels may create structural gaps; missing data are not zero.'),
      '09_half_year_patterns':('Is the reporting-period distribution uneven?', 'Pool known counts by Jan–Jun and Jul–Dec for top diseases; show semester-year totals separately.', f'Bluetongue has {bt_share:.1%} of known counts in Jul–Dec. Shares describe reporting periods, not monthly onset seasonality.', 'Use these contrasts to design region-specific seasonal follow-up.', 'Pooled hemispheres, reporting lag, one-off peaks, and incomplete coverage can mimic seasonality. No monthly or significance claim is supported.'),
      '10_exploratory_anomalies':('Which recent semester counts depart from their historical same-half baseline?', 'Prior five consecutive same-half years only; log1p(known counts / disease-specific observed countries), median and scaled MAD; screen positive robust scores >3.5. Skip incomplete-count periods and zero MAD.',f'{len(flags)} flags among {len(t["anomaly_scores"])} eligible comparisons. The figure prioritises selected diseases with at least three observed countries and 50 known counts, one region per disease.','Use flags as a reproducible triage list for source review; five points are too few for calibrated tail probabilities.','No p-values, false-positive calibration, causal inference or forecast validation. Country composition may change, denominator is a reporting proxy, and excluded ambiguous groups can lower counts.'),
      '11_country_ranking':('Are known counts concentrated in a few countries?', 'Rank cumulative known country counts after regional de-duplication.',f'The top five countries account for {co.head(5).outbreaks.sum()/total:.1%}.','Concentration motivates country-level sensitivity checks.','No livestock denominators, comparable surveillance capacity or uniform outbreak definition.'),
    }
    details=[]
    for dz in PRIORITY:
        g=t['disease_year'].loc[lambda v:v.Disease.eq(dz)].dropna(subset=['outbreaks'])
        if len(g):
            v=g.loc[g.outbreaks.idxmax()];details.append(f'{short(dz)}: {int(v.Year)} ({v.outbreaks:,.0f})')
    fm=flags[flags.Disease.eq('Foot and mouth disease virus (Inf. with)')&flags['World region'].eq('Asia')&flags.Year.eq(2022)]
    if len(fm):
        v=fm.iloc[0]
        note=list(notes['10_exploratory_anomalies'])
        note[2]+=f' For Asia/FMD {int(v.Year)} half {int(v.half)}, observed counts per reporting country are {v.observed_per_country:,.1f} versus historical median {v.baseline_per_country:,.1f} ({v.fold_vs_baseline:.1f}×); {v.largest_contributing_country} contributes {v.largest_country_known_counts:,.0f} known counts.'
        notes['10_exploratory_anomalies']=tuple(note)
    notes['12_priority_disease_regions']=('Which regions drive changes in selected diseases?', 'Separate annual regional sums for six observed source disease labels; HPAI categories remain separate; no absent years are filled.', 'Peak observed global years: '+ '; '.join(details)+'.', 'These peaks identify focused disease-region case studies for Challenge 6.', 'Coverage and source definitions change; the non-poultry HPAI label begins in 2017 and cannot be compared with an invented pre-2017 zero baseline.')
    return findings,notes


def run(input_path=None, output=None, policy='prefer-both'):
    out=Path(output or ROOT/'eda/output');(out/'charts').mkdir(parents=True,exist_ok=True);(out/'tables').mkdir(exist_ok=True)
    preferred=ROOT/'data/cleaned_summary.csv'
    path=Path(input_path) if input_path else (preferred if preferred.exists() else ROOT/'WAHIS_data.csv')
    s,audit,conflicts,orphans=load_and_validate(path,policy)
    if not len(s) or not s['count'].notna().any():
        raise ValueError('No known eligible summary counts: supply a cleaned export with observed counts.')
    audit['input_mode']='cleaned export' if path!=ROOT/'WAHIS_data.csv' else 'audited raw fallback; upstream export not present'
    t=build_tables(s);climate,climate_panel=climate_audit(s,ROOT);audit['climate']=climate
    for name,df in t.items():df.to_csv(out/'tables'/f'{name}.csv',index=False)
    conflicts.to_csv(out/'tables/conflicting_summary_rows.csv',index=False);orphans.to_csv(out/'tables/orphan_detail_groups.csv',index=False)
    # Climate join audit is small, preserves observed WAHIS country-semesters only.
    climate_panel.to_csv(out/'tables/climate_join_audit.csv',index=False)
    (out/'audit.json').write_text(json.dumps(audit,indent=2))
    make_charts(s,t,out);findings,notes=interpretations(t,audit)
    lines=['# Part 3: exploratory reported disease occurrence, 2005–2024','',
           'Source and objective: [WOAH Challenge 6](https://data-integration-department-woah.github.io/WOAH-Datathon/challenges.html). This analysis addresses retrospective trends and unusual variation; monthly analysis and validated early warnings require additional data.','',
           f'Input: `{path.name}`; SHA-256 `{audit["sha256"]}`. Mode: {audit["input_mode"]}. Summary policy: `{policy}`.','',
           f'Known selected counts total {audit["selected_known_outbreaks"]:,.0f} across {audit["countries"]} countries/territories and {audit["diseases"]} unchanged disease labels.','', '## Supported insights','']+[f'{i}. {v}' for i,v in enumerate(findings,1)]
    lines+=['','## Data integrity and assumptions','',
      'One selected row is an administrative-division × disease × subtype × country × semester summary, not one outbreak. New outbreaks is the count field; cases, deaths, animal units, events and outbreak IDs are excluded from totals. Distinct subtype rows are assumed additive as in the upstream notebook, pending a WOAH data dictionary; mixed subtype strings are retained intact and never exploded.',
      'Only blank-Species, blank/dash-Outbreak_id rows qualify. Prefer Both animal categories per subtype group; otherwise sum the existing Domestic/Wild summaries, without inventing an absent category. If any present category count is unknown, its group count stays unknown. A numeric fallback is therefore a known reported count, not evidence both categories were surveyed. Both-only sensitivity is reported above.',
      f'Verified copies removed: {audit["verified_duplicate_rows_removed"]:,}; same-key/same-count summaries removed: {audit["same_key_same_count_rows_removed"]:,}; conflicting summary keys: {audit["conflicting_summary_keys_excluded"]:,}, quarantined with their subtype groups. Missing selected counts: {audit["selected_unknown_groups"]:,}. Detail groups without any summary: {audit["detail_groups_without_summary"]:,}; excluded without zero inference.',
      'Middle East member countries are assigned to Middle East for disjoint analysis. Exact copies are removed after reassignment; unmatched records are retained except ambiguous summary keys, which are excluded and exported for adjudication. This changes geographic categorisation, not original files.',
      'No disease relabelling is applied. Year is restricted to 2005–2024 despite later years in the raw input. Dates represent reporting semesters, not validated outbreak onset dates. Both 2024 halves are observed, but submission completeness/cutoff cannot be established from this file. All sums are known reported contributions and can be partial.',
      'Missing disease–time/geography combinations remain unknown in analytical tables and heatmaps. No country-disease absence is inferred from reporting another disease. Counts per observed reporting country are a sensitivity proxy, not an incidence rate or complete adjustment for surveillance.',
      'The existing script.ipynb creates synthetic zero summaries in its first cleaning cell but ignores them in its later analysis, which also fills absent disease periods with zero. Its stated model results are not adopted or revalidated here. Teammate files are unchanged.','',
      '## Chart questions and interpretation','']
    for name,fields in notes.items():
        if not (out/'charts'/f'{name}.png').exists():continue
        lines += [f'### {name}','',f'![{name}](output/charts/{name}.png)','']
        for label,value in zip(['Research question','Method','Observation','Interpretation','Limitations'],fields):lines.append(f'**{label}:** {value}\n')
    lines += ['## Integration with Parts 1 and 2','',
      'There is no saved cleaned WAHIS summary dataset. Export `data/cleaned_summary.csv` with the original required columns listed in `analysis.py`, including subtype and category, and `is_synthetic_summary` where applicable. Keep missing New outbreaks missing; do not infer zeros. Use --input for another path. The EDA validates, reselects and audits this input without modifying it. A Both-only export cannot reconstruct category summaries already discarded; its scope will differ from the raw prefer-both fallback. Confirm the final summary policy and subtype additivity with teammates before adopting presentation totals.','',
      '## Climate feasibility and follow-up','',f'Complete existing climate coverage matches {climate.get("complete_climate_matches",0):,} of {climate.get("observed_country_semesters",0):,} observed country-semesters ({climate.get("match_pct",0):.2f}%). Unmatched countries: {", ".join(climate.get("unmatched_countries",[]))}. Full provenance and shared ISO3 mappings are in output/audit.json.','',
      'The existing monthly climate file is usable for six-month country-level joins only when all six months and variables are present. Shared ISO3 mappings (historical territories or subdivisions) need adjudication; do not combine WAHIS counts blindly by ISO3. Other climate CSVs were inspected but not mixed into this join. No association is claimed from match coverage.',
      'Next: resolve ambiguous summary counts and obtain the WOAH dictionary; validate top country reports and renamed disease definitions; estimate disease-region negative-binomial trends with disease-specific reporting and exposure denominators, residual checks and multiplicity control; assess half-year effects by hemisphere; obtain onset dates for monthly seasonality. For climate, use country/half-year fixed effects, temperature and rainfall anomalies, contiguous semester lags and country-clustered inference, then time-ordered holdout validation with baselines/thresholds fitted on training data only. Assess associations separately from causal or predictive claims.','',
      'Challenge 6 relevance: annual/disease/regional series describe reported trends; coverage and selection sensitivity distinguish measurement changes from plausible epidemiological signals; the trailing historical baseline provides an interpretable review list. These are retrospective exploratory outputs, not operational early-warning thresholds.']
    (ROOT/'eda/report.md').write_text('\n'.join(lines))
    (out/'interpretations.json').write_text(json.dumps({'findings':findings,'charts':notes},indent=2))
    print(json.dumps({k:v for k,v in audit.items() if k not in ['climate','countries_reassigned_to_middle_east']},indent=2))
    return s,t,audit,findings,notes

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--summary-policy',choices=['prefer-both','both-only'],default='prefer-both')
    args=parser.parse_args();run(args.input,args.output,args.summary_policy)
