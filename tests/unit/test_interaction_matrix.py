from __future__ import annotations

import pytest
import numpy as np, pandas as pd
from itertools import product
from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.plan import AnalysisPlan
from datawork.core.method_registry import list_methods

rng=np.random.default_rng(2026)

def continuous_two():
    n=30
    return pd.DataFrame({'y':np.r_[rng.normal(0,1,n),rng.normal(1,1.4,n)],'group':['A']*n+['B']*n,'x':np.r_[rng.normal(size=n),rng.normal(size=n)]})
def continuous_three():
    n=24
    return pd.DataFrame({'y':np.concatenate([rng.normal(i,1,n) for i in range(3)]),'group':sum(([g]*n for g in ['A','B','C']),[] )})
def paired():
    n=36; a=rng.normal(5,1,n); b=a+rng.normal(.6,.7,n)
    return pd.DataFrame({'before':a,'after':b})
def factorial(k=2):
    rows=[]
    factors=[f'F{i+1}' for i in range(k)]
    for levels in product(['L0','L1'], repeat=k):
      for rep in range(12):
        eff=sum((i+1)*(lv=='L1') for i,lv in enumerate(levels))
        row={f:v for f,v in zip(factors,levels)}; row['y']=10+eff+rng.normal(0,1); rows.append(row)
    return pd.DataFrame(rows),factors
def categorical_2x2():
    rows=[]
    for a,b,n in [('A','yes',18),('A','no',12),('B','yes',8),('B','no',22)]: rows += [{'a':a,'b':b}]*n
    return pd.DataFrame(rows)
def proportions(k=3):
    rows=[]
    for i,g in enumerate(list('ABC')[:k]):
      p=.25+.2*i
      for _ in range(50): rows.append({'outcome':'yes' if rng.random()<p else 'no','group':g})
    return pd.DataFrame(rows)
def paired_cat():
    vals=['A','B','C']; n=90
    r1=rng.choice(vals,n,p=[.4,.35,.25]); r2=[]; r3=[]
    for v in r1:
      r2.append(v if rng.random()<.7 else rng.choice(vals))
      r3.append(v if rng.random()<.65 else rng.choice(vals))
    return pd.DataFrame({'r1':r1,'r2':r2,'r3':r3})
def repeated(mixed=False):
    rows=[]; sid=0
    for g in (['A','B'] if mixed else ['A']):
      for _ in range(14):
        sid+=1; u=rng.normal(0,.7)
        for ti,t in enumerate(['T1','T2','T3']):
          rows.append({'subject':f'S{sid}','group':g,'time':t,'y':8+(g=='B')*1.2+ti*.8+(g=='B')*ti*.25+u+rng.normal(0,.3)})
    return pd.DataFrame(rows)
def stratified():
    rows=[]
    for s in ['S1','S2','S3','S4']:
      for exp,out,n in [(1,1,15),(1,0,8),(0,1,7),(0,0,16)]: rows += [{'outcome':out,'exposure':exp,'strata':s}]*n
    return pd.DataFrame(rows)
def regression(categorical=False,multi=False):
    n=260; x=rng.normal(size=n); g=rng.choice(['A','B'],n)
    latent=.8*x+.5*(g=='B')+rng.normal(size=n)
    if multi: y=np.where(latent<-.6,'low',np.where(latent<.7,'mid','high'))
    elif categorical: y=(latent>0).astype(int)
    else: y=2+1.7*x+.8*(g=='B')+rng.normal(0,.7,n)
    return pd.DataFrame({'y':y,'x':x,'group':g})
def lmm():
    rows=[]
    for c in range(18):
      u=rng.normal(0,.8); sl=rng.normal(0,.15); cond='A' if c<9 else 'B'
      for t in range(6): rows.append({'cluster':f'C{c}','condition':cond,'time':float(t),'y':3+.6*t+.5*(cond=='B')+u+sl*t+rng.normal(0,.25)})
    return pd.DataFrame(rows)
def manova_df():
    rows=[]
    for g,off in [('A',0),('B',1),('C',2)]:
      for _ in range(30):
        x=rng.normal(); rows.append({'g':g,'y1':off+x+rng.normal(0,.5),'y2':.5*off-.4*x+rng.normal(0,.5)})
    return pd.DataFrame(rows)


def manova_factorial(k=2):
    rows=[]
    factors=[f'MF{i+1}' for i in range(k)]
    for levels in product(['L0','L1'], repeat=k):
      for _ in range(16):
        eff=sum((i+1)*(lv=='L1') for i,lv in enumerate(levels))
        latent=rng.normal()
        row={f:v for f,v in zip(factors,levels)}
        row['y1']=5+eff+latent+rng.normal(0,.5)
        row['y2']=2+.65*eff+.45*latent+rng.normal(0,.55)
        rows.append(row)
    return pd.DataFrame(rows),factors

def case(name):
    if name=='descriptive_statistics': return pd.DataFrame({'y':rng.normal(size=30),'x':rng.normal(size=30)}),dict(dependent_variables=['y','x'])
    if name=='one_sample_ttest': return pd.DataFrame({'y':rng.normal(.4,1,40)}),dict(dependent_variables=['y'],test_value=0)
    if name in {'welch_ttest','independent_ttest','mann_whitney_u'}: return continuous_two(),dict(dependent_variables=['y'],fixed_factors=['group'])
    if name in {'paired_ttest','wilcoxon_signed_rank','pearson_correlation','spearman_correlation','kendall_correlation'}: return paired(),dict(dependent_variables=['before','after'])
    if name in {'oneway_anova','welch_anova','kruskal_wallis'}: return continuous_three(),dict(dependent_variables=['y'],fixed_factors=['group'])
    if name=='twoway_anova':
      d,f=factorial(2); return d,dict(dependent_variables=['y'],fixed_factors=f,estimate_marginal_means=True,emm_factors=f)
    if name=='threeway_anova':
      d,f=factorial(3); return d,dict(dependent_variables=['y'],fixed_factors=f)
    if name=='multifactor_anova':
      d,f=factorial(4); return d,dict(dependent_variables=['y'],fixed_factors=f,method_parameters={'factor_model_order':'4'})
    if name=='ancova':
      d=continuous_three(); d['baseline']=rng.normal(size=len(d)); d['y']+=.7*d['baseline']; return d,dict(dependent_variables=['y'],fixed_factors=['group'],covariates=['baseline'],estimate_marginal_means=True,emm_factors=['group'])
    if name=='linear_regression': return regression(),dict(dependent_variables=['y'],fixed_factors=['group'],covariates=['x'],estimate_marginal_means=True,emm_factors=['group'])
    if name=='logistic_regression': return regression(categorical=True),dict(dependent_variables=['y'],fixed_factors=['group'],covariates=['x'],method_parameters={'success_level':'1'})
    if name in {'chi_square_independence','fisher_exact','barnard_exact','boschloo_exact'}: return categorical_2x2(),dict(fixed_factors=['a','b'])
    if name=='chi_square_goodness_of_fit':
      d=pd.DataFrame({'cat':['A']*20+['B']*30+['C']*40}); return d,dict(fixed_factors=['cat'],expected_proportions=[1/3]*3)
    if name in {'exact_binomial_test','one_sample_proportion_ztest'}:
      d=proportions(1).drop(columns='group'); d=d.rename(columns={'outcome':'flag'}); return d,dict(fixed_factors=['flag'],method_parameters={'success_level':'yes'})
    if name=='mcnemar_test':
      n=80; a=rng.integers(0,2,n); b=np.where(rng.random(n)<.8,a,1-a); return pd.DataFrame({'pre':a,'post':b}),dict(dependent_variables=['pre','post'])
    if name in {'two_proportion_ztest','k_proportion_chi_square'}:
      d=proportions(2 if name=='two_proportion_ztest' else 3); return d,dict(dependent_variables=['outcome'],fixed_factors=['group'],method_parameters={'success_level':'yes'})
    if name=='cochran_q_test':
      n=80; base=rng.integers(0,2,n); d=pd.DataFrame({f'q{i}':np.where(rng.random(n)<.7,base,1-base) for i in range(1,4)}); return d,dict(dependent_variables=['q1','q2','q3'])
    if name in {'bowker_symmetry','stuart_maxwell','cohen_kappa'}: return paired_cat(),dict(dependent_variables=['r1','r2'])
    if name in {'cochran_mantel_haenszel','breslow_day'}: return stratified(),dict(dependent_variables=['outcome'],fixed_factors=['exposure','strata'])
    if name=='fleiss_kappa': return paired_cat(),dict(dependent_variables=['r1','r2','r3'])
    if name=='cochran_armitage_trend':
      d=proportions(3); d['group']=d['group'].map({'A':'low','B':'mid','C':'high'}); return d,dict(dependent_variables=['outcome'],fixed_factors=['group'],method_parameters={'success_level':'yes','level_order':'low,mid,high','scores':'0,1,2'})
    if name in {'multinomial_logistic_regression','ordinal_logistic_regression'}:
      d=regression(multi=True); params={'level_order':'low,mid,high'} if name.startswith('ordinal') else {}; return d,dict(dependent_variables=['y'],fixed_factors=['group'],covariates=['x'],method_parameters=params)
    if name in {'repeated_measures_anova','friedman_test'}: return repeated(),dict(dependent_variables=['y'],subject_id='subject',repeated_factor='time',estimate_marginal_means=(name=='repeated_measures_anova'),emm_factors=['time'] if name=='repeated_measures_anova' else [])
    if name=='linear_mixed_model': return lmm(),dict(dependent_variables=['y'],fixed_factors=['condition'],covariates=['time'],random_factors=['cluster'],random_slopes=['time'],estimate_marginal_means=True,emm_factors=['condition'])
    if name=='oneway_manova': return manova_df(),dict(dependent_variables=['y1','y2'],fixed_factors=['g'])
    if name=='twoway_manova':
      d,f=manova_factorial(2); return d,dict(dependent_variables=['y1','y2'],fixed_factors=f)
    if name=='threeway_manova':
      d,f=manova_factorial(3); return d,dict(dependent_variables=['y1','y2'],fixed_factors=f,method_parameters={'follow_up_mode':'none','covariance_test':False,'normality_test':False})
    if name=='multifactor_manova':
      d,f=manova_factorial(4); return d,dict(dependent_variables=['y1','y2'],fixed_factors=f,method_parameters={'factor_model_order':'4','multivariate_test':'pillai','follow_up_mode':'none','covariance_test':False,'normality_test':False,'correlation_diagnostics':False})
    if name=='mixed_anova': return repeated(mixed=True),dict(dependent_variables=['y'],fixed_factors=['group'],subject_id='subject',repeated_factor='time',estimate_marginal_means=True,emm_factors=['group','time'])
    raise KeyError(name)



def test_every_registered_method_has_a_valid_interaction_path():
    service = AnalysisService()
    preflight = PreflightService()
    failures = []
    for method in list_methods(runnable_only=True):
        try:
            frame, kwargs = case(method.name)
            raw = {**kwargs, "method": method.name}
            report = preflight.inspect(frame, raw)
            if not report.ready:
                failures.append((method.name, "preflight", [(item.code, item.message) for item in report.issues]))
                continue
            result = service.run(frame, AnalysisPlan(**raw))
            assert result is not None
        except Exception as exc:  # pragma: no cover - aggregated assertion reports method name
            failures.append((method.name, type(exc).__name__, str(exc)))
    assert not failures, failures


@pytest.mark.parametrize("method_name", [
    "logistic_regression", "exact_binomial_test", "one_sample_proportion_ztest",
    "two_proportion_ztest", "k_proportion_chi_square", "cochran_mantel_haenszel",
    "breslow_day", "cochran_armitage_trend",
])
def test_invalid_requested_success_level_is_blocked_before_execution(method_name):
    frame, kwargs = case(method_name)
    raw = {**kwargs, "method": method_name}
    raw["method_parameters"] = {**raw.get("method_parameters", {}), "success_level": "不存在的水平"}
    report = PreflightService().inspect(frame, raw)
    assert not report.ready
    assert any(item.code == "unknown_requested_level" for item in report.issues)


@pytest.mark.parametrize("method_name", ["cochran_armitage_trend", "ordinal_logistic_regression"])
def test_invalid_ordered_levels_are_blocked_before_execution(method_name):
    frame, kwargs = case(method_name)
    raw = {**kwargs, "method": method_name}
    raw["method_parameters"] = {**raw.get("method_parameters", {}), "level_order": "错误,顺序,集合"}
    report = PreflightService().inspect(frame, raw)
    assert not report.ready
    assert any(item.code == "invalid_level_order" for item in report.issues)


@pytest.mark.parametrize("method_name", ["cochran_mantel_haenszel", "breslow_day"])
def test_stratified_methods_require_binary_exposure(method_name):
    frame, kwargs = case(method_name)
    frame = frame.copy()
    frame["exposure"] = np.resize([0, 1, 2], len(frame))
    report = PreflightService().inspect(frame, {**kwargs, "method": method_name})
    assert not report.ready
    assert any(item.code == "binary_exposure_required" for item in report.issues)


def test_factorial_empty_cells_are_reported_before_execution():
    frame, factors = factorial(2)
    frame = frame[~((frame[factors[0]] == "L1") & (frame[factors[1]] == "L1"))]
    raw = {"method": "twoway_anova", "dependent_variables": ["y"], "fixed_factors": factors}
    report = PreflightService().inspect(frame, raw)
    assert not report.ready
    assert any(item.code == "empty_factorial_cells" for item in report.issues)


def test_batch_preflight_validates_every_real_subtask():
    frame = continuous_two()
    frame["batch"] = np.tile(np.repeat(["good", "bad"], len(frame) // 4), 2)
    frame.loc[frame["batch"] == "bad", "group"] = "A"
    raw = {"method": "welch_ttest", "dependent_variables": ["y"], "fixed_factors": ["group"], "split_by": ["batch"]}
    report = PreflightService().inspect(frame, raw)
    assert report.ready
    assert report.batch_summary["problem_group_count"] == 1
    failed = [item for item in report.batch_summary["groups"] if not item["ready"]]
    assert failed and any("水平" in reason for reason in failed[0]["reasons"])


def test_batch_preflight_blocks_when_every_subtask_is_invalid():
    frame = continuous_two()
    frame["batch"] = np.where(np.arange(len(frame)) % 2 == 0, "A", "B")
    frame["group"] = frame["batch"]
    raw = {"method": "welch_ttest", "dependent_variables": ["y"], "fixed_factors": ["group"], "split_by": ["batch"]}
    report = PreflightService().inspect(frame, raw)
    assert not report.ready
    assert report.batch_summary["ready_group_count"] == 0


def test_every_method_blocks_missing_roles_bad_types_and_unknown_parameters():
    preflight = PreflightService()
    failures = []
    categorical_outcomes = {
        "logistic_regression", "mcnemar_test", "two_proportion_ztest", "k_proportion_chi_square",
        "cochran_q_test", "bowker_symmetry", "stuart_maxwell", "cochran_mantel_haenszel",
        "breslow_day", "cohen_kappa", "fleiss_kappa", "cochran_armitage_trend",
        "multinomial_logistic_regression", "ordinal_logistic_regression",
    }
    for method in list_methods(runnable_only=True):
        frame, kwargs = case(method.name)
        raw = {**kwargs, "method": method.name}
        omissions = []
        if method.min_dependent_vars:
            omissions.append(("dependent_variables", []))
        if method.min_fixed_factors:
            omissions.append(("fixed_factors", []))
        if method.min_covariates:
            omissions.append(("covariates", []))
        if method.min_random_factors:
            omissions.append(("random_factors", []))
        if method.requires_subject_id:
            omissions.append(("subject_id", None))
        if method.requires_repeated_factor:
            omissions.append(("repeated_factor", None))
        if method.requires_any_predictor:
            bad = {**raw, "fixed_factors": [], "covariates": []}
            if preflight.inspect(frame, bad).ready:
                failures.append((method.name, "missing predictors"))
        for field, value in omissions:
            if preflight.inspect(frame, {**raw, field: value}).ready:
                failures.append((method.name, f"missing {field}"))
        if raw.get("fixed_factors"):
            bad_frame = frame.copy()
            bad_frame[raw["fixed_factors"][0]] = "only"
            if preflight.inspect(bad_frame, raw).ready:
                failures.append((method.name, "constant factor"))
        if raw.get("dependent_variables") and method.name not in categorical_outcomes:
            bad_frame = frame.copy()
            bad_frame[raw["dependent_variables"][0]] = "not numeric"
            if preflight.inspect(bad_frame, raw).ready:
                failures.append((method.name, "nonnumeric dependent"))
        bad_parameters = {**raw, "method_parameters": {**raw.get("method_parameters", {}), "__unknown__": 1}}
        if preflight.inspect(frame, bad_parameters).ready:
            failures.append((method.name, "unknown parameter"))
    assert not failures, failures
