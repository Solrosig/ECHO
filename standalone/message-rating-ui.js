import {RATING_SCALE} from './study-session.js';
import {MESSAGE_RATING_VERSION} from './message-rating.js';
const forms=new Set();
export function refreshMessageRatings(){for(const f of forms){if(f.root.isConnected)f.update();else forms.delete(f);}}
export function messageRatingForm(audio,session,order,sync){
 const root=document.createElement('details');root.className='message-rating';
 const summary=document.createElement('summary');summary.textContent='Rate this voice message';root.append(summary);
 const intro=document.createElement('p');intro.textContent='Rate the voice you hear. The engine and requested emotion are visible, so these ratings are exploratory.';
 const form=document.createElement('form'),fieldset=document.createElement('fieldset');form.append(fieldset);
 let heard=false,plays=0,started=performance.now(),touched=new Set();const inputs={};
 for(const [key,title,min,max,step,anchors] of [
  ['valence','How positive or negative does the voice sound?',-100,100,1,['Negative','Neutral','Positive']],
  ['arousal','How much energy does the voice convey?',-100,100,1,['Low energy','Neutral','High energy']],
  ['naturalness','How natural does the voice sound?',1,5,1,['Very artificial','Moderate','Very natural']],
  ['target_match','How closely does it match your chosen emotion?',1,5,.5,['Not at all','Moderately','Very closely']]
 ]){
  const wrap=document.createElement('div');wrap.className='message-scale';const label=document.createElement('label'),output=document.createElement('output'),input=document.createElement('input');
  input.type='range';input.min=min;input.max=max;input.step=step;input.value=(min+max)/2;input.id='rating-'+crypto.randomUUID();label.htmlFor=input.id;label.textContent=title;output.htmlFor=input.id;output.textContent='Not rated';
  const ruler=document.createElement('div');ruler.className='message-ruler';ruler.setAttribute('aria-hidden','true');
  const ticks=key==='target_match'?9:5;for(let i=0;i<ticks;i++){const tick=document.createElement('span');tick.textContent=String(min+(max-min)*i/(ticks-1));ruler.append(tick);}
  const ends=document.createElement('div');ends.className='message-anchors';for(const text of anchors){const s=document.createElement('span');s.textContent=text;ends.append(s);}
  const midpoint=document.createElement('button');midpoint.type='button';midpoint.className='rating-midpoint';midpoint.textContent=min===-100?'Choose neutral (0)':'Choose midpoint (3)';
  const changed=()=>{touched.add(key);output.textContent=min===-100?input.value:Number(input.value).toFixed(step===.5?1:0)+' / 5';};input.addEventListener('input',changed);midpoint.addEventListener('click',()=>{input.value=(min+max)/2;changed();});
  inputs[key]=input;wrap.append(label,output,input,ruler,ends,midpoint);fieldset.append(wrap);
 }
 const submit=document.createElement('button');submit.type='submit';submit.className='primary';submit.textContent='Save this message rating';fieldset.append(submit);
 const status=document.createElement('p');status.className='message-rating-status';status.setAttribute('role','status');root.append(intro,form,status);
 const update=()=>{const queued=Boolean(session.ratings?.[order]);fieldset.disabled=!heard||queued;status.textContent=queued?(session.saved_rating_orders?.includes(order)?'Rating received by the database.':'Rating saved in this browser; waiting for the database. Use Retry saving if needed.'):'Listen to the whole message at normal speed, then rate all four scales.';summary.textContent=queued?'Your voice message rating':'Rate this voice message';};
 audio.addEventListener('play',()=>plays++);audio.addEventListener('ended',()=>{if(audio.playbackRate===1){heard=true;update();}});
 form.addEventListener('submit',event=>{event.preventDefault();if(session.ratings?.[order])return;try{
  if(!heard||touched.size!==4)throw new Error('Listen to the whole message and rate all four scales. The midpoint buttons also count as a rating.');
  const rating={valence:Number(inputs.valence.value)/100,arousal:Number(inputs.arousal.value)/100,naturalness:Number(inputs.naturalness.value),target_match:Number(inputs.target_match.value),rating_scale:RATING_SCALE,version:MESSAGE_RATING_VERSION,completed_audio:true,play_count:plays,elapsed_s:(performance.now()-started)/1000,created_utc:new Date().toISOString()};
  void sync.rate(order,rating).then(update);update();
 }catch(e){status.textContent=e.message;}});
 forms.add({root,update});update();return root;
}
