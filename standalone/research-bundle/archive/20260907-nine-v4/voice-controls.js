import {ENGINE_PROFILES,CALIBRATION_VERSION} from './calibration-profiles.js';
export const CONTROL_VERSION=CALIBRATION_VERSION;
export const EMOTIONS={
  happy:{name:'Happy',v:.6,a:.6,description:'Positive · high energy'},
  upset:{name:'Upset',v:-.6,a:.6,description:'Negative · high energy'},
  sad:{name:'Sad',v:-.6,a:-.6,description:'Negative · low energy'},
  calm:{name:'Calm',v:.6,a:-.6,description:'Positive · low energy'},
};
export const ENGINES={
  chatterbox:{name:'Chatterbox',voice:'RAVDESS actor 03',mechanism:'Reference conditioning + expressiveness',pitch:false,detail:'Emotion reference audio with native exaggeration and pacing guidance. These controls do not provide a direct valence dial.'},
  zipvoice:{name:'ZipVoice',voice:'RAVDESS actor 03',mechanism:'Reference-conditioned flow matching',pitch:false,detail:'Uses a reference utterance to guide delivery. Emotional transfer is an experimental use of reference conditioning, not a built-in Russell-quadrant command.'},
  styletts2:{name:'StyleTTS2',voice:'RAVDESS actor 03',mechanism:'Reference style + diffusion',pitch:false,detail:'Blends an acoustic reference style with a diffusion-sampled style. The reference and the sampled style can both affect the result.'},
  cosyvoice2:{name:'CosyVoice2',voice:'RAVDESS actor 03',mechanism:'Instruction-conditioned speech generation',pitch:false,detail:'An emotion instruction specifies delivery; one fixed neutral reference specifies the speaker. This separates the instruction from reference emotion.'},
  parlertts:{name:'Parler-TTS',voice:'Jon',mechanism:'Text description of delivery',pitch:false,detail:'A description requests emotion and speaking style while keeping the named speaker fixed. Instruction adherence must be evaluated by listeners.'},

  kokoro:{name:'Kokoro',voice:'af_heart',mechanism:'Neural speech synthesis · 82M parameters',pitch:true,detail:'Native speed control; ECHO adds pitch shifting after synthesis and calibrates the output level. Pitch shifting is external DSP, not a native emotion feature. Voice: af_heart.'},
  piper:{name:'Piper',voice:'en_US-ljspeech-medium',mechanism:'VITS neural speech synthesis',pitch:true,detail:'Native inverse length scale controls timing; ECHO adds pitch shifting after synthesis and calibrates the output level. Noise settings and voice identity stay fixed. Pitch is external DSP.'},
};
const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
export function controlsFor({emotion,intensity=1,engine,condition='preset',custom}){
  if(!Object.hasOwn(EMOTIONS,emotion)||!Object.hasOwn(ENGINES,engine))throw new Error('Choose an emotion and an engine.');
  if(!Number.isFinite(intensity)||intensity<0||intensity>1)throw new Error('Intensity must be between 0 and 1.');
  if(!['preset','neutral','rate','gain','pitch','custom'].includes(condition))throw new Error('Unknown control condition.');
  if(condition==='pitch'&&!ENGINES[engine].pitch)throw new Error('This engine does not expose independent pitch control.');
  const native=['chatterbox','zipvoice','styletts2','cosyvoice2','parlertts'].includes(engine);
  if(native&&!['preset','neutral'].includes(condition))throw new Error('This engine compares native emotion conditioning with its neutral setting.');
  const e=EMOTIONS[emotion],profile=ENGINE_PROFILES[engine][emotion],base={rate:1,gain:.8,pitch:null,pitch_semitones:0};
  let p={rate:1+(profile.rate-1)*intensity,gain:.8+(profile.gain-.8)*intensity,pitch:null,pitch_semitones:(profile.pitch_semitones||0)*intensity};
  if(condition==='neutral')p={...base};
  if(['rate','gain'].includes(condition))p={...base,[condition]:p[condition]};
  if(condition==='pitch')p={...base,pitch:p.pitch,pitch_semitones:p.pitch_semitones};
  if(condition==='custom'){
    if(!custom||['rate','gain'].some(k=>!Number.isFinite(custom[k]))||!Number.isFinite(custom.pitch_semitones??custom.pitch))throw new Error('Enter valid control values.');
    p={rate:custom.rate,gain:custom.gain,pitch:null,pitch_semitones:custom.pitch_semitones??custom.pitch};
  }
  p={rate:clamp(p.rate,.65,1.4),gain:clamp(p.gain,.4,1.3),pitch:null,pitch_semitones:clamp(p.pitch_semitones,-4,4)};
  const names={happy:'Q1',upset:'Q2',sad:'Q3',calm:'Q4'},instructions={happy:'Speak in a happy, upbeat and energetic tone.',upset:'Speak in an angry, agitated and tense tone.',sad:'Speak in a sad, subdued and downhearted tone.',calm:'Speak in a calm, warm and relaxed tone.'};
  const a=condition==='neutral'?0:e.a;
  const conditioning=native?{version:'echo-native-conditioning-v1',seed:666,reference:condition==='neutral'||engine==='cosyvoice2'?'neutral':names[emotion],instruction:condition==='neutral'?'Speak in a neutral tone.':instructions[emotion],exaggeration:.3+.55*(a+1)/2,cfg_weight:.6-.3*(a+1)/2,alpha:.3,beta:.7,diffusion_steps:5}:null;
  return {...p,conditioning,engine,voice:ENGINES[engine].voice,words_per_minute:null,length_scale:engine==='piper'?1/p.rate:null,condition,
    emotion,emotion_source:'user',target:{valence:e.v,arousal:e.a},intensity,control_version:CONTROL_VERSION,
    pitch_mechanism:'external DSP, SoundTouchJS 2.1.1',level_reference:'relative-gated active RMS, -22.50 dBFS before gain',
    mapping_status:native?'Native conditioning implementation; no human coherence result is available.':'Acoustically calibrated preset; perceived emotion and naturalness await independent listener validation.'};
}
export function validateText(text){
  if(typeof text!=='string'||!text.trim()||text.length>800)throw new Error('Enter 1–800 characters of English text.');
  return text.trim();
}
export function dialogueMessages(text,emotion,history=[]){
  validateText(text);if(!Object.hasOwn(EMOTIONS,emotion))throw new Error('Choose an emotion.');
  const e=EMOTIONS[emotion];
  return [{role:'system',content:`You write short conversational replies for a speech prototype. The USER has explicitly chosen ${e.name}: ${e.description}. Keep that requested tone, while remaining helpful and respectful. Never infer, diagnose or change the user's emotional target. Do not invent facts. Reply in one or two short English sentences, maximum 45 words. Return only the spoken reply, without labels, JSON or stage directions.`},
    ...history.slice(-6).filter(m=>['user','assistant'].includes(m.role)).map(m=>({role:m.role,content:String(m.content).slice(0,800)})),{role:'user',content:text}];
}

// Bound neural input segments so the tokenizer cannot silently truncate a long utterance.
export function speechChunks(text,max=200){
 const words=validateText(text).split(/\s+/),chunks=[];let current='';
 for(const word of words){if(word.length>max)throw new Error('Use ordinary English words; a text token is too long.');if(current&&(current.length+word.length+1>max)){chunks.push(current);current='';}current+=(current?' ':'')+word;}
 if(current)chunks.push(current);return chunks;
}
