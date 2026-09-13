// The reply check (echo-reply-check-v1). Before a conversation reply is voiced, the same language model reads the user's
// message and the reply, without being told the chosen emotion, and answers three closed questions about what the reply's
// words show (observable rubric items, as Kumar et al. 2026 recommend for LLM judges). The server maps feeling and energy
// to a quadrant and compares it with the user's chosen emotion. A reply that does not respond to the message, or misses the
// quadrant, is generated again with the next seed, at most twice; if no attempt passes, the best-scoring attempt is used
// and flagged (the author's choice, 2026-09-13). The judge is the reply's own model, so it is not an independent
// instrument; its agreement with independent labels is measured in the 2026-09-13 screen.
export const REPLY_CHECK_VERSION='echo-reply-check-v1';
export const CHECK_GENERATION={temperature:0,seed:666,max_tokens:60};
export const CHECK_FORMAT={type:'json_object'};
const TARGET={happy:{feeling:'positive',energy:'high'},upset:{feeling:'negative',energy:'high'},sad:{feeling:'negative',energy:'low'},calm:{feeling:'positive',energy:'low'}};

const RUBRIC=[
  'You check one reply written for a speech prototype. Read the user\'s last message and the reply, then answer three questions about what the reply\'s words show. Do not judge whether the reply is good or polite.',
  'responds: "yes" if the reply responds to what the user actually said: it helps with or asks about a request, answers a question, returns a greeting, or reacts to the news the user shared. "no" if it misreads the message (for example, it thanks the user for an offer they did not make), treats the user\'s news as its own, or talks about something else.',
  'feeling: "positive" or "negative" for the feeling the reply\'s words express; "neutral" only if they express no feeling at all.',
  'energy: "high" if the reply sounds excited, agitated, urgent or intense (for example exclamation marks, or short, sharp sentences); "low" if it sounds quiet, weary, gentle or unhurried.',
  'Return only this JSON object: {"responds": "yes" or "no", "feeling": "positive", "negative" or "neutral", "energy": "high" or "low"}'
].join('\n');

export function replyCheckMessages(message,reply,history=[]){
  const earlier=(Array.isArray(history)?history:[]).slice(-2).filter(m=>['user','assistant'].includes(m?.role))
    .map(m=>`${m.role==='user'?'User':'Reply'} earlier: "${String(m.content).slice(0,400)}"`);
  return [{role:'system',content:RUBRIC},{role:'user',content:[...earlier,`User's last message: "${String(message).slice(0,800)}"`,`Reply: "${String(reply).slice(0,800)}"`].join('\n')}];
}

// The judge's answer, or null when it is not the requested JSON with allowed values.
export function parseVerdict(content){
  const found=String(content??'').match(/\{[\s\S]*?\}/);if(!found)return null;
  let data;try{data=JSON.parse(found[0]);}catch{return null;}
  const pick=(value,allowed)=>{const word=String(value??'').trim().toLowerCase();return allowed.includes(word)?word:null;};
  const responds=pick(data?.responds,['yes','no']),feeling=pick(data?.feeling,['positive','negative','neutral']),energy=pick(data?.energy,['high','low']);
  return responds&&feeling&&energy?{responds:responds==='yes',feeling,energy}:null;
}

// A verdict against the chosen emotion: its quadrant, whether it passes, and a score for choosing among failed attempts.
export function judgeReply(verdict,emotion){
  const target=TARGET[emotion];if(!target)throw new Error('Choose an emotion.');
  const quadrant=Object.keys(TARGET).find(e=>TARGET[e].feeling===verdict.feeling&&TARGET[e].energy===verdict.energy)??null;
  return {...verdict,quadrant,passed:verdict.responds&&quadrant===emotion,score:(verdict.responds?2:0)+(verdict.feeling===target.feeling?1:0)+(verdict.energy===target.energy?1:0)};
}

// The attempt a reply comes from: the first that passes; else, when the last attempt could not be checked, that one;
// else the highest score, the earliest on a tie.
export function acceptedAttempt(verdicts){
  const passed=verdicts.findIndex(v=>v?.passed);if(passed>=0)return {status:'passed',index:passed};
  const last=verdicts.length-1;if(!verdicts[last])return {status:'unavailable',index:last};
  let best=0;verdicts.forEach((v,i)=>{if(v&&v.score>(verdicts[best]?.score??-1))best=i;});
  return {status:'failed',index:best};
}
