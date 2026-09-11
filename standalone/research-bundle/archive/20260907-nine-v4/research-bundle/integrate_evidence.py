"""Run AFTER analyse_ratings.py. Never treat repeated ratings as new waveforms.
No human observations are generated. Empty input produces readiness output only.
"""
from pathlib import Path
import csv,json,argparse,io
from collections import defaultdict
import numpy as np
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parent

def write(path,rows,fields):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def integrate(analysis,out,evidence):
 out.mkdir(parents=True,exist_ok=True)
 if any(out.iterdir()):raise ValueError('Choose an empty output folder; previous results must not be overwritten.')
 source=analysis/'joined-ratings.csv';matrix=list(csv.DictReader(io.StringIO(evidence.read_text())));byhash={r['sha256']:r for r in matrix}
 if len(byhash)!=45 or len(matrix)!=45:raise ValueError('Expected 45 distinct frozen waveforms')
 report=json.loads((analysis/'summary.json').read_text());rows=list(csv.DictReader(io.StringIO(source.read_text()))) if source.exists() else []
 if len(rows)!=report['included_ratings']:raise ValueError('Analysis summary and joined rows disagree')
 if not rows:(out/'READINESS.json').write_text(json.dumps({'status':'READY; no eligible human responses. No estimates or shortlist computed.','verified_acoustic_rows':45,'expected_human_output':'joined-ratings.csv from analyse_ratings.py'},indent=2));return
 joined=[]
 for r in rows:
  a=byhash[r['audio_sha256']]
  if a['item_id']!=r['item_id'] or a['engine']!=r['engine']:raise ValueError('Acoustic/response identity mismatch')
  joined.append(r|{k:v for k,v in a.items() if k not in ['emotion','condition','engine','item_id','text_id','sha256']})
 write(out/'ratings-with-acoustics.csv',joined,list(joined[0]))
 # Cell uncertainty resamples listeners within the fixed engine/target cell.
 profiles=[];rng=np.random.default_rng(20260909)
 for engine in sorted({r['engine'] for r in joined}):
  for emotion in ['happy','upset','sad','calm']:
   rs=[r for r in joined if (r['engine'],r['emotion'],r['condition'])==(engine,emotion,'preset')]
   if not rs:continue
   row={'engine':engine,'emotion':emotion,'n_listeners':len(rs)}
   for metric in ['target_error','valence_error','arousal_error','naturalness','target_match']:
    a=np.array([float(r[metric]) for r in rs]);ci=np.quantile(rng.choice(a,(10000,len(a)),replace=True).mean(axis=1),[.025,.975]) if len(a)>1 else [None,None]
    row.update({metric+'_mean':a.mean(),metric+'_ci_low':ci[0],metric+'_ci_high':ci[1]})
   profiles.append(row)
 write(out/'engine-emotion-profiles.csv',profiles,list(profiles[0]))
 # Shared neutral is reused within each participant. One row per preset pair.
 people=defaultdict(list)
 for r in joined:people[r['participant_id']].append(r)
 pairs=[]
 for pid,rs in people.items():
  neutral={r['engine']:r for r in rs if r['condition']=='neutral'}
  for r in rs:
   if r['condition']!='preset':continue
   n=neutral[r['engine']];ev=abs(float(n['valence'])-float(r['target_valence']))/2;ea=abs(float(n['arousal'])-float(r['target_arousal']))/2
   pairs.append({'participant_id':pid,'engine':r['engine'],'emotion':r['emotion'],'preset_sha256':r['audio_sha256'],'neutral_sha256':n['audio_sha256'],'delta_valence':ev-float(r['valence_error']),'delta_arousal':ea-float(r['arousal_error']),'delta_target':(ev+ea)/2-float(r['target_error']),'f0_delta_st':12*np.log2(float(r['acoustic_f0_median_hz'])/float(n['acoustic_f0_median_hz'])),'rms_delta_db':float(r['acoustic_rms_dbfs'])-float(n['acoustic_rms_dbfs']),'duration_ratio':float(r['acoustic_duration_s'])/float(n['acoustic_duration_s'])})
 write(out/'paired-mechanism-evidence.csv',pairs,list(pairs[0]))
 # Aggregate each engine/target cell to avoid counting acoustic copies as observations.
 cells=[]
 for engine in sorted({r['engine'] for r in pairs}):
  for emotion in ['happy','upset','sad','calm']:
   rs=[r for r in pairs if (r['engine'],r['emotion'])==(engine,emotion)]
   if not rs:continue
   cells.append({'engine':engine,'emotion':emotion,'n_listeners':len(rs)}|{k:float(np.mean([r[k] for r in rs])) for k in ['delta_valence','delta_arousal','delta_target','f0_delta_st','rms_delta_db','duration_ratio']})
 write(out/'mechanism-cell-means.csv',cells,list(cells[0]))
 assoc=[]
 for physical in ['f0_delta_st','rms_delta_db','duration_ratio']:
  for perceptual in ['delta_valence','delta_arousal','delta_target']:
   x=[r[physical] for r in cells];y=[r[perceptual] for r in cells];rho=float(spearmanr(x,y).statistic) if np.std(x)>0 and np.std(y)>0 else None
   assoc.append({'acoustic':physical,'perception':perceptual,'n_cells':len(cells),'spearman_rho_descriptive':rho,'scope':'pooled dependent engine/emotion cells; no significance test, no causal interpretation'})
 write(out/'descriptive-acoustic-associations.csv',assoc,list(assoc[0]))
 # Predeclared product shortlist: equal weights across four emotions. Incomplete coverage blocks selection.
 scores=[]
 for engine in ['kokoro','chatterbox','styletts2','cosyvoice2','parlertts']:
  subset=[r for r in joined if r['engine']==engine and r['condition']=='preset'];emos={e:[r for r in subset if r['emotion']==e] for e in ['happy','upset','sad','calm']}
  if any(not v for v in emos.values()):continue
  scores.append({'engine':engine,'target_error':float(np.mean([np.mean([float(r['target_error']) for r in rs]) for rs in emos.values()])),'naturalness':float(np.mean([np.mean([float(r['naturalness']) for r in rs]) for rs in emos.values()]))})
 short={}
 for margin in [0,.025,.05,.1]:
  remaining=scores[:];chosen=[]
  while remaining and len(chosen)<3:
   best=min(r['target_error'] for r in remaining);near=[r for r in remaining if r['target_error']<=best+margin];pick=min(near,key=lambda r:(-r['naturalness'],r['target_error'],r['engine']));chosen.append(pick['engine']);remaining.remove(pick)
  short[str(margin)]=chosen
 (out/'PROVISIONAL_SHORTLIST.json').write_text(json.dumps({'status':'provisional product selection; not independent validation' if len(scores)==5 else 'INCOMPLETE COVERAGE; do not change Explore shortlist','rule':'Equal emotion weights; within 0.05 E_T of best remaining choose highest naturalness, then smaller error, then alphabetical deterministic tie break. Repeat to three. Margin is a product policy, not perceptual equivalence.','primary_margin':.05,'candidate_scores':scores,'sensitivity_shortlists':short if len(scores)==5 else {},'technical_eligibility':'Five current live engines. Confirm runtime availability separately before deployment.','uncertainty':'Inspect listener confidence intervals and emotion coverage. Do not claim a statistically established winner from the shortlist.'},indent=2))
 # Empirical figures only when eligible human data are present.
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,ax=plt.subplots(figsize=(7,4));ps=list(csv.DictReader(io.StringIO((analysis/'participant-contrasts.csv').read_text())));rng=np.random.default_rng(20260909)
 for x,(key,label) in enumerate([('target_improvement','H1: target improvement'),('arousal_improvement','Arousal improvement'),('valence_improvement','Valence improvement'),('arousal_minus_valence_improvement','H2: arousal − valence')]):
  a=np.array([float(r[key]) for r in ps]);mean=a.mean();ci=np.quantile(rng.choice(a,(10000,len(a)),replace=True).mean(axis=1),[.025,.975]);ax.errorbar(x,mean,yerr=[[mean-ci[0]],[ci[1]-mean]],fmt='o',color='#234c67',capsize=4)
 ax.axhline(0,color='gray',lw=.8);ax.set_xticks(range(4),['H1','Δ arousal','Δ valence','H2']);ax.set_ylabel('Mean improvement with participant bootstrap 95% CI');ax.set_title(f'Observed listeners: N={len(ps)}; fixed materials');fig.tight_layout();fig.savefig(out/'human-primary-contrasts.png',dpi=220);plt.close(fig)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence',type=Path,default=ROOT/'current-phase/CURRENT_45_EVIDENCE_MATRIX.csv');a=p.parse_args();integrate(a.analysis,a.output,a.evidence)
