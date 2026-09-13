// The conversation prompt, built only on this server. The 1.5.0 prompt stays untouched in voice-controls.js, whose
// hash PROTOCOL_FREEZE_V2.json pins. v3 names each emotion with ECHO's quadrant wording (prompts/q1-q4.txt) and adds one
// delivery cue and one example reply; the author chose it on 2026-09-11 from a screen of four prompts. v4a and v4b are the
// 2026-09-13 candidates against replies that miss what the user said (evidence 2026-09-12-emotion-coherence-investigation):
// an answer-first rule with four examples (a request, a question, a greeting and news), and in v4b a one-word reading of the
// message that the server removes before the reply is checked or spoken.
import {EMOTIONS,validateText} from '../voice-controls.js';

export const PROMPT_VERSIONS={v3:'echo-dialogue-v3',v4a:'echo-dialogue-v4a',v4b:'echo-dialogue-v4b'};
export const DEFAULT_PROMPT='v3';
export const DIALOGUE_PROMPT_VERSION=PROMPT_VERSIONS[DEFAULT_PROMPT];

const FEELING={
  happy:{label:'HAPPY and ENERGETIC',axes:'positive feeling, high energy',tone:'upbeat, warm, lively, a little excited',
    delivery:'Sound excited: use lively, enthusiastic wording and at least one exclamation mark.',
    example:'Rain tomorrow? Great, that is the perfect excuse for a cosy afternoon with a good film!'},
  upset:{label:'UPSET and AGITATED',axes:'negative feeling, high energy',tone:'tense, irritated or anxious, clearly bothered',
    delivery:'Sound agitated: use tense, frustrated wording in short, sharp sentences.',
    example:'Rain again? That wrecks the whole afternoon I had planned, and nobody warned us!'},
  sad:{label:'SAD and SUBDUED',axes:'negative feeling, low energy',tone:'downcast, quiet, weary, low spirits',
    delivery:'Sound low: use heavy, weary wording and slow phrasing, without exclamation marks.',
    example:'Rain again tomorrow... I suppose the afternoon will just feel long and grey.'},
  calm:{label:'CALM and CONTENT',axes:'positive feeling, low energy',tone:'settled, warm, unhurried, quietly pleased',
    delivery:'Sound relaxed: use gentle, unhurried wording, without exclamation marks.',
    example:'Rain tomorrow afternoon sounds fine; a slow, quiet afternoon indoors would be nice.'},
};

// v4's example messages; none of them is in the 2026-09-13 screen's test set.
export const EXAMPLE_MESSAGES={request:'Can you help me move this sofa on Saturday?',question:'Which should I start first, the dishes or the laundry?',
  greeting:'Hi, nice to see you.',news:'They closed the park for repairs.'};
const EXAMPLES={
  happy:{request:'Yes, I would love to help with the sofa on Saturday! What time should I come over?',question:'Start with the dishes, and the laundry will feel easy after that!',
    greeting:'Hi! It is so good to see you again!',news:'Repairs? The park will be even nicer when it opens again!'},
  upset:{request:'Moving a sofa is such a hassle. Fine, I will help, but we start early.',question:'The dishes. Leaving them there only makes the mess worse!',
    greeting:'Hi. Sorry, today has been one annoying problem after another.',news:'Closed again? That was the one quiet place left around here!'},
  sad:{request:'I can help with the sofa on Saturday, though I feel rather worn out lately.',question:'Maybe the dishes first. Everything seems like so much to get through today.',
    greeting:'Hi. It is nice to see you, even if I am feeling a little low.',news:'Oh no, the park was one of the few places that lifted my mood.'},
  calm:{request:'Of course, I can help with the sofa on Saturday. Just tell me what time suits you.',question:'Start with the dishes and let the laundry run while you tidy up.',
    greeting:'Hi, it is lovely to see you. How has your day been?',news:'That is fine, a little patience and the park will be ready again soon.'},
};

function v3System(f){
  return [
    `You write short spoken replies for a speech prototype. The user has chosen the emotion your reply must express: ${f.label} (${f.axes}): ${f.tone}.`,
    'Express that emotion in your own reaction to the user\'s message, even when the message is ordinary or neutral. Direct any negative feeling at the situation, never at the user.',
    f.delivery,
    `For example, to the message "It is supposed to rain tomorrow afternoon." a reply with this emotion could be: "${f.example}" Do not reuse the example's words.`,
    'Never infer, diagnose or change the user\'s emotional target. Do not invent facts. Reply in one or two short English sentences, maximum 45 words. Return only the spoken reply, without labels, JSON or stage directions.',
  ].join(' ');
}

function v4System(emotion,act){
  const f=FEELING[emotion],e=EXAMPLES[emotion];
  const examples=Object.entries(EXAMPLE_MESSAGES).map(([kind,message])=>act?`To "${message}":\n${kind}\n${e[kind]}`:`To "${message}": "${e[kind]}"`);
  return [
    `You write short spoken replies for a speech prototype. The user has chosen the emotion your reply must express: ${f.label} (${f.axes}): ${f.tone}.`,
    'First respond to what the user actually said or asked: help with a request or ask what they need, answer a question, return a greeting, or react to their news. Never thank the user for an offer they did not make, and never present their news as your own.',
    'Let the emotion colour that response, even when the message is ordinary or neutral. Direct any negative feeling at the situation, never at the user.',
    f.delivery,
    ...(act?['Before the reply, write one word on its own line that says what the user\'s last message is: greeting, question, request, news or other. Write the reply on the next line. That word is removed before the reply is spoken.']:[]),
    'Examples with this emotion (do not reuse their words or their sentence shapes):',
    ...examples,
    `Never infer, diagnose or change the user's emotional target. Do not invent facts. Reply in one or two short English sentences, maximum 45 words. ${act?'Apart from the first word, return only the spoken reply':'Return only the spoken reply'}, without labels, JSON or stage directions.`,
  ].join('\n');
}

export function dialogueMessages(text,emotion,history=[],{variant=DEFAULT_PROMPT}={}){
  validateText(text);if(!Object.hasOwn(EMOTIONS,emotion))throw new Error('Choose an emotion.');
  if(!Object.hasOwn(PROMPT_VERSIONS,variant))throw new Error('Unknown conversation prompt.');
  const system=variant==='v3'?v3System(FEELING[emotion]):v4System(emotion,variant==='v4b');
  return [{role:'system',content:system},
    ...history.slice(-6).filter(m=>['user','assistant'].includes(m.role)).map(m=>({role:m.role,content:String(m.content).slice(0,800)})),{role:'user',content:text}];
}

// A v4b reply begins with the model's one-word reading of the message. Removed: a first line of one word (the model may
// pick a word outside the list, as "Joke" in the lab's plumbing check), or a listed word followed by a colon or a spaced
// dash. A reply without either is left as it is.
export function stripActLabel(text){
  const reply=String(text??'').trim();
  const found=reply.match(/^[\s"'“*_]*(?:(greeting|question|request|news|other)[\s"'”*_.]*?(?::|\s[-–—]\s)|([A-Za-z]{2,15})[\s"'”*_.:]*?\r?\n)\s*/i);
  const rest=found?reply.slice(found[0].length).trim():'';
  return rest?{reply:rest,act:(found[1]||found[2]).toLowerCase()}:{reply,act:null};
}

// The quoted example leads the model to wrap some whole replies in quotation marks (27 of 204 in the screen).
// Only such a wrapping pair is removed; no word changes.
export function unwrapQuotedReply(text){
  const reply=String(text??'').trim(),inner=reply.slice(1,-1);
  return reply.length>1&&/^["“]/.test(reply)&&/["”]$/.test(reply)&&!/["“”]/.test(inner)?inner.trim():reply;
}
