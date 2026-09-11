"""Validate human CSVs and analyse participant-level paired improvements.
No observations are invented. Technical tests and incomplete/exposed sessions are excluded.
Usage: python analyse_ratings.py --responses responses --output analysis
"""
import argparse,csv,json,math,io
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import ttest_1samp
ROOT=Path(__file__).resolve().parent

def calculate_scores(rating,target):
 ev=abs(float(rating['valence'])-target['valence'])/2
 ea=abs(float(rating['arousal'])-target['arousal'])/2
 return {'valence_error':ev,'arousal_error':ea,'target_error':(ev+ea)/2}

def participant_contrasts(joined):
 pairs=[]
 for pid,rows in joined.items():
  base={(r['text_id'],r['engine']):r for r in rows if r['condition']=='neutral'}
  if len(base)!=9:raise ValueError('Expected nine distinct neutral controls')
  contrasts=[]
  for r in rows:
   if r['condition']!='preset':continue
   b=base[(r['text_id'],r['engine'])]
   # The baseline was heard once. Re-evaluate that perception against this target;
   # never reuse its disclosed target-match response for another emotion.
   scores=calculate_scores(b,{'valence':r['target_valence'],'arousal':r['target_arousal']})
   contrasts.append({'target_improvement':scores['target_error']-r['target_error'],'arousal_improvement':scores['arousal_error']-r['arousal_error'],'valence_improvement':scores['valence_error']-r['valence_error']})
  if len(contrasts)!=18:raise ValueError('Expected eighteen complete preset/baseline pairs per participant')
  d={k:float(np.mean([c[k] for c in contrasts])) for k in contrasts[0]};d['arousal_minus_valence_improvement']=d['arousal_improvement']-d['valence_improvement'];d['participant_id']=pid;pairs.append(d)
 return pairs

def summary(values,rng):
 a=np.asarray(values,float);n=len(a)
 if n==0:return {'n_participants':0,'mean':None,'ci95':None,'p_one_sided':None}
 ci=np.quantile(np.mean(rng.choice(a,size=(10000,n),replace=True),axis=1),[.025,.975]).tolist() if n>=2 else None
 p=float(ttest_1samp(a,0,alternative='greater').pvalue) if n>=5 and np.std(a)>0 else None
 return {'n_participants':n,'mean':float(a.mean()),'ci95_participant_bootstrap_conditional_on_fixed_materials':ci,'p_one_sided':p}

def analyse(folder,out,rating_scale=None):
 key=json.loads((ROOT/'private/analysis-key.json').read_text());manifest=json.loads((ROOT.parent/'public/study/manifest.json').read_text());items={j['item_id']:j for j in key['items']};blocks={b['block_id']:b for b in manifest['blocks']};groups=defaultdict(dict);excluded=[]
 for path in sorted(folder.glob('*.csv')):
  for r in csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))):
   r['rating_scale']=r.get('rating_scale') or 'va-0.05_match-1_naturalness-1_v1'
   if rating_scale and r['rating_scale']!=rating_scale:continue
   pid=r.get('participant_id','');identity=(r.get('order'),r.get('item_id'))
   if r.get('record_type')!='human_response' or pid.startswith('TEST-'):
    excluded.append({'participant_id':pid,'reason':'not a human research response','file':path.name});continue
   if not pid.startswith('P-'):raise ValueError(f'Invalid anonymous ID in {path.name}')
   if identity in groups[pid] and groups[pid][identity]!=r:raise ValueError(f'Conflicting repeated export for {pid}; resolve explicitly')
   groups[pid][identity]=r
 joined={}
 for pid,rd in groups.items():
  rows=list(rd.values());reason=None
  if len(rows)!=27:reason='incomplete session (27 responses required)'
  elif any(r.get('previously_used_studio')!='false' for r in rows):reason='prior exposure to named studio voices'
  elif any(r.get('comfortable_english')!='true' or r.get('headphones')!='true' or r.get('completed_audio')!='true' for r in rows):reason='eligibility or completed playback not confirmed'
  if reason:excluded.append({'participant_id':pid,'reason':reason});continue
  if len({(r['group'],r['seed'],r['study_version'],r['rating_scale'],r.get('collection_version','legacy')) for r in rows})!=1:raise ValueError(f'Inconsistent session metadata: {pid}')
  if rows[0]['study_version']!=key['study_version']:raise ValueError('Wrong stimulus version')
  g=int(rows[0]['group'])-1
  if g<0 or g>=16:raise ValueError('Invalid group')
  expected={(bid,item) for bid in manifest['groups'][g] for item in blocks[bid]['item_ids']}
  if {(r['block_id'],r['item_id']) for r in rows}!=expected or sorted(int(r['order']) for r in rows)!=list(range(1,28)):raise ValueError(f'Unexpected/missing/duplicate trials for {pid}')
  joined[pid]=[]
  for r in rows:
   for k in ['valence','arousal']:
    v=float(r[k]);
    if not math.isfinite(v) or not -1<=v<=1:raise ValueError('Invalid emotional rating')
   naturalness=float(r['naturalness']);match=float(r['target_match'])
   if not math.isfinite(naturalness) or not naturalness.is_integer() or not 1<=naturalness<=5:raise ValueError('Invalid naturalness rating')
   scale=r['rating_scale'];factor=2 if scale=='va-0.01_match-0.5_naturalness-1_v2' else 1
   if scale not in ['va-0.01_match-0.5_naturalness-1_v2','va-0.05_match-1_naturalness-1_v1']:raise ValueError('Unknown rating scale')
   if not math.isfinite(match) or not 1<=match<=5 or not (match*factor).is_integer():raise ValueError('Invalid target-match rating')
   j=items[r['item_id']];b=blocks[r['block_id']]
   if r.get('audio_sha256') and r['audio_sha256']!=j['sha256']:raise ValueError('Rating and frozen waveform hash disagree')
   joined[pid].append({**r,**calculate_scores(r,b['target']), 'audio_sha256':j['sha256'],'engine':j['engine'],'voice':j['voice'],'condition':j['condition'],'emotion':b['target']['name'].lower(),'text_id':j['text_id'],'target_valence':b['target']['valence'],'target_arousal':b['target']['arousal']})
 scales=sorted({r['rating_scale'] for rows in joined.values() for r in rows})
 if len(scales)>1:raise ValueError('Mixed rating scales. Separate cohorts or pass --rating-scale with one exact scale identifier.')
 out.mkdir(parents=True,exist_ok=True);contrasts=participant_contrasts(joined);rng=np.random.default_rng(20260907)
 h1=summary([r['target_improvement'] for r in contrasts],rng);h2=summary([r['arousal_minus_valence_improvement'] for r in contrasts],rng)
 pvals=[h1['p_one_sided'],h2['p_one_sided']]
 if all(x is not None for x in pvals):
  order=np.argsort(pvals);adjusted=np.empty(2);running=0
  for rank,i in enumerate(order):running=max(running,min(1,pvals[i]*(2-rank)));adjusted[i]=running
  for i,h in enumerate([h1,h2]):h['p_holm_two_hypotheses']=float(adjusted[i])
 report={'rating_scales':scales,'collection_versions':sorted({r.get('collection_version','legacy') for rows in joined.values() for r in rows}),'study_version':key['study_version'],'included_participants':len(joined),'included_ratings':sum(map(len,joined.values())),'excluded_sessions_or_rows':excluded,'H1_preset_reduces_target_error':h1,'H2_arousal_improves_more_than_valence':h2,'inference_scope':'Participant-level paired estimates, conditional on one fixed English carrier text and one voice/rendition per engine-condition; the same neutral perception is reused for two targets with dependence retained inside each participant mean. No population inference over speakers or texts.','test_assumptions':'One-sided t tests of participant mean contrasts against zero, only N>=5 and nonconstant data. Check independence/distribution before interpreting. Holm adjustment over the two hypotheses. Target N=32 is resource based; neither N=5 nor N=16 guarantees adequate power. Interpret early-stop or assumption-violating samples descriptively.','human_data_status':'observed responses' if joined else 'NO ELIGIBLE HUMAN DATA; no hypothesis conclusion'}
 (out/'summary.json').write_text(json.dumps(report,indent=2));
 for name,rows in [('joined-ratings',sum(joined.values(),[])),('participant-contrasts',contrasts)]:
  if rows:
   with (out/f'{name}.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 # Equal-weight participant means within each engine/emotion/condition; no per-clip pseudo-replication.
 by_cell=defaultdict(lambda:defaultdict(list))
 for pid,rows in joined.items():
  for r in rows:by_cell[(r['engine'],r['emotion'],r['condition'])][pid].append(r)
 cells=[]
 for cell,people in sorted(by_cell.items()):
  row=dict(zip(['engine','emotion','condition'],cell));row['n_participants']=len(people)
  for metric in ['target_error','valence_error','arousal_error','naturalness','target_match']:row['mean_'+metric]=float(np.mean([np.mean([float(r[metric]) for r in rs]) for rs in people.values()]))
  cells.append(row)
 if cells:
  with (out/'exploratory-engine-emotion-controls.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=cells[0]);w.writeheader();w.writerows(cells)
 print(json.dumps({k:report[k] for k in ['included_participants','included_ratings','human_data_status']},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--responses',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rating-scale',help='Analyse only this scale; mixed scale cohorts are otherwise rejected');a=p.parse_args();analyse(a.responses,a.output,a.rating_scale)
