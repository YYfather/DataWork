#!/usr/bin/env python3
"""Regenerate the deterministic CSV inputs for the golden validation suite.

This script does not update expected values. Changing a dataset intentionally
requires an independent statistical review and a separately reviewed manifest
update.
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'golden_datasets'/'data'; DATA.mkdir(parents=True,exist_ok=True)

def save(name, df):
    path=DATA/f'{name}.csv'; df.to_csv(path,index=False); return path.name

rng=np.random.default_rng(4901)
# data
one=pd.DataFrame({'y':[8.2,9.1,10.3,11.0,9.8,10.7,8.9,11.4,10.1,9.6,10.8,9.4]})
save('one_sample',one)
ind=pd.DataFrame({'y':[4.2,5.1,4.8,5.5,4.9,5.2,4.6,5.0, 6.1,6.5,7.0,5.9,6.7,6.4,7.2,6.0,6.8,6.3], 'group':['A']*8+['B']*10})
save('independent_groups',ind)
paired=pd.DataFrame({'before':[10,12,9,11,13,8,14,10,12,11,9,13], 'after':[11,13,10,12,14,9,15,11,13,12,10,15]})
save('paired',paired)
groups=pd.DataFrame({'y':[2.1,2.5,2.9,3.0,2.7,3.2, 4.0,4.4,4.1,4.8,4.5,4.7,4.3, 5.8,6.1,5.5,6.4,6.0,5.9,6.3,6.2], 'group':['A']*6+['B']*7+['C']*8})
save('three_groups',groups)
rows=[]
for a in ['A1','A2']:
 for b in ['B1','B2']:
  n={('A1','B1'):7,('A1','B2'):9,('A2','B1'):8,('A2','B2'):10}[(a,b)]
  for i in range(n):
   y=10+1.4*(a=='A2')+0.8*(b=='B2')+0.6*(a=='A2' and b=='B2')+rng.normal(0,.55)
   rows.append((a,b,y))
f2=pd.DataFrame(rows,columns=['A','B','y']); save('factorial_two',f2)
rows=[]
for a in ['A1','A2']:
 for b in ['B1','B2']:
  for c in ['C1','C2']:
   for i in range(7):
    y=8+1.0*(a=='A2')+.7*(b=='B2')+.5*(c=='C2')+.4*(a=='A2' and b=='B2')+.35*(a=='A2' and c=='C2')+rng.normal(0,.6)
    rows.append((a,b,c,y))
f3=pd.DataFrame(rows,columns=['A','B','C','y']); save('factorial_three',f3)
rows=[]
for g,off in [('A',0),('B',1.2),('C',2.0)]:
 for x in np.linspace(-1.5,1.5,12): rows.append((g,x,5+off+.9*x+rng.normal(0,.35)))
anc=pd.DataFrame(rows,columns=['group','baseline','y']); save('ancova',anc)
x=np.linspace(-3,3,40); corr=pd.DataFrame({'x':x,'y':1.4*x+np.sin(x)*.4}); save('correlation',corr)
reg=pd.DataFrame({'x':np.linspace(-2,2,60)}); reg['group']=np.where(np.arange(60)%2==0,'A','B'); reg['y']=3+1.7*reg.x+.8*(reg.group=='B')+np.cos(np.arange(60))*.2; save('linear_regression',reg)
log=pd.DataFrame({'x':np.linspace(-2.8,2.8,100)}); log['group']=np.where(np.arange(100)%2==0,'A','B'); latent=-.4+1.1*log.x+.55*(log.group=='B'); probs=1/(1+np.exp(-latent)); # deterministic Bernoulli-ish pattern
log['y']=(np.mod(np.arange(100)*37,100)/100 < probs).astype(int); save('logistic',log)
# categorical counts
def rows_counts(columns, tuples):
 out=[]
 for vals,n in tuples:
  out += [dict(zip(columns,vals))]*n
 return pd.DataFrame(out)
cat22=rows_counts(['a','b'],[(('A','yes'),18),(('A','no'),12),(('B','yes'),8),(('B','no'),22)]); save('contingency_2x2',cat22)
gof=pd.DataFrame({'cat':['A']*20+['B']*30+['C']*40}); save('goodness_of_fit',gof)
pbin=pd.DataFrame({'pre':[1]*30+[1]*10+[0]*6+[0]*34,'post':[1]*30+[0]*10+[1]*6+[0]*34}); save('paired_binary',pbin)
onebin=pd.DataFrame({'flag':['yes']*34+['no']*26}); save('one_binary',onebin)
prop2=rows_counts(['group','outcome'],[(('A','yes'),18),(('A','no'),32),(('B','yes'),31),(('B','no'),19)]); save('proportions_two',prop2)
prop3=rows_counts(['group','outcome'],[(('A','yes'),12),(('A','no'),28),(('B','yes'),22),(('B','no'),18),(('C','yes'),30),(('C','no'),10)]); save('proportions_three',prop3)
q=pd.DataFrame({'q1':[1,1,0,0,1,0,1,0,1,0,1,0,1,1,0,0,1,0,1,0], 'q2':[1,0,0,0,1,1,1,0,1,0,0,0,1,1,1,0,1,0,1,1], 'q3':[1,0,1,0,1,1,0,0,1,1,0,0,1,0,1,0,1,1,1,1]}); save('cochran_q',q)
pcat=rows_counts(['r1','r2'],[(('A','A'),20),(('A','B'),5),(('A','C'),2),(('B','A'),3),(('B','B'),18),(('B','C'),6),(('C','A'),1),(('C','B'),4),(('C','C'),21)]); pcat['r3']=np.resize(['A','A','B','B','C','C','A','B','C'],len(pcat)); save('paired_multiclass',pcat)
rows=[]
for s,counts in [('S1',(15,8,7,16)),('S2',(13,9,8,15)),('S3',(18,7,9,14)),('S4',(14,10,6,17))]:
 for (exp,out),n in zip([(1,1),(1,0),(0,1),(0,0)],counts): rows += [{'outcome':out,'exposure':exp,'strata':s}]*n
strat=pd.DataFrame(rows); save('stratified',strat)
# ratings wide, deterministic
ratings=pd.DataFrame({'r1':list('AABBCABCABCCABABCCAB'), 'r2':list('AABBCABCABBCABABCCAC'), 'r3':list('ABBBCABCABCCABABCAAB')}); save('ratings',ratings)
trend=rows_counts(['dose','outcome'],[(('low','yes'),8),(('low','no'),32),(('mid','yes'),18),(('mid','no'),22),(('high','yes'),30),(('high','no'),10)]); save('trend',trend)
# multinomial ordinal deterministic
multi=pd.DataFrame({'x':np.linspace(-2.5,2.5,120)}); multi['group']=np.where(np.arange(120)%2==0,'A','B'); latent=multi.x+.4*(multi.group=='B')+np.sin(np.arange(120))*.25; multi['y']=np.where(latent<-.55,'low',np.where(latent<.75,'mid','high')); save('multiclass_regression',multi)
# repeated
rows=[]
for sid in range(1,13):
 u=(sid%4-1.5)*.18
 for ti,t in enumerate(['T1','T2','T3']): rows.append((f'S{sid}',t,6+u+ti*.9+((sid*ti)%3-.8)*.08))
rep=pd.DataFrame(rows,columns=['subject','time','y']); save('repeated',rep)
rows=[]
for cluster in range(1,17):
 cond='A' if cluster<=8 else 'B'; u=(cluster%5-2)*.22; slope=((cluster*3)%7-3)*.025
 for t in range(5): rows.append((f'C{cluster}',cond,float(t),3+.55*t+.65*(cond=='B')+u+slope*t+np.sin(cluster+t)*.06))
lmm=pd.DataFrame(rows,columns=['cluster','condition','time','y']); save('mixed_model',lmm)
rows=[]
for g,off in [('A',0),('B',.8),('C',1.5)]:
 for i in range(18):
  z=np.sin(i*.7); rows.append((g,2+off+z+.15*np.cos(i),1+.55*off-.35*z+.12*np.sin(i*1.3)))
man1=pd.DataFrame(rows,columns=['g','y1','y2']); save('manova_one',man1)
rows=[]
for a in ['A1','A2']:
 for b in ['B1','B2']:
  for i in range(14):
   e=1.0*(a=='A2')+.65*(b=='B2')+.45*(a=='A2' and b=='B2'); z=np.sin(i*.55)
   rows.append((a,b,4+e+z+.12*np.cos(i),2+.6*e-.4*z+.1*np.sin(i*1.2)))
man2=pd.DataFrame(rows,columns=['A','B','y1','y2']); save('manova_two',man2)
rows=[]
for a in ['A1','A2']:
 for b in ['B1','B2']:
  for c in ['C1','C2']:
   ai=a=='A2'; bi=b=='B2'; ci=c=='C2'
   for i in range(12):
    e1=.8*ai+.55*bi+.4*ci+.3*(ai and bi)+.24*(ai and ci)+.18*(bi and ci)+.15*(ai and bi and ci)
    e2=.35*ai+.75*bi+.5*ci-.20*(ai and bi)+.28*(ai and ci)-.16*(bi and ci)+.22*(ai and bi and ci)
    z=np.sin(i*.6); w=np.cos(i*.43)
    rows.append((a,b,c,5+e1+.75*z+.16*w,3+e2-.28*z+.55*w+.08*np.sin(i*1.1)))
man3=pd.DataFrame(rows,columns=['A','B','C','y1','y2']); save('manova_three',man3)
rows=[]
for g in ['A','B']:
 for sid0 in range(1,11):
  sid=f'{g}{sid0}'; u=(sid0%4-1.5)*.16
  for ti,t in enumerate(['T1','T2','T3']): rows.append((sid,g,t,7+.8*(g=='B')+.7*ti+.22*(g=='B')*ti+u+np.sin(sid0+ti)*.05))
mix=pd.DataFrame(rows,columns=['subject','group','time','y']); save('mixed_anova',mix)

print(f'Regenerated golden CSV files in {DATA}')
