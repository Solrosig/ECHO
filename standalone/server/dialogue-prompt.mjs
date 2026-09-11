// The conversation prompt, built only on this server. The 1.5.0 prompt stays untouched in voice-controls.js, whose
// hash PROTOCOL_FREEZE_V2.json pins. This version names each emotion with ECHO's quadrant wording (prompts/q1-q4.txt)
// and adds one delivery cue; a rule fixed before the 2026-09-11 screen chose it from four candidates.
import {EMOTIONS,validateText} from '../voice-controls.js';

export const DIALOGUE_PROMPT_VERSION='echo-dialogue-v2';

const FEELING={
  happy:{label:'HAPPY and ENERGETIC',axes:'positive feeling, high energy',tone:'upbeat, warm, lively, a little excited',
    delivery:'Sound excited: use lively, enthusiastic wording and at least one exclamation mark.'},
  upset:{label:'UPSET and AGITATED',axes:'negative feeling, high energy',tone:'tense, irritated or anxious, clearly bothered',
    delivery:'Sound agitated: use tense, frustrated wording in short, sharp sentences.'},
  sad:{label:'SAD and SUBDUED',axes:'negative feeling, low energy',tone:'downcast, quiet, weary, low spirits',
    delivery:'Sound low: use heavy, weary wording and slow phrasing, without exclamation marks.'},
  calm:{label:'CALM and CONTENT',axes:'positive feeling, low energy',tone:'settled, warm, unhurried, quietly pleased',
    delivery:'Sound relaxed: use gentle, unhurried wording, without exclamation marks.'},
};

export function dialogueMessages(text,emotion,history=[]){
  validateText(text);if(!Object.hasOwn(EMOTIONS,emotion))throw new Error('Choose an emotion.');
  const f=FEELING[emotion];
  const system=[
    `You write short spoken replies for a speech prototype. The user has chosen the emotion your reply must express: ${f.label} (${f.axes}): ${f.tone}.`,
    'Express that emotion in your own reaction to the user\'s message, even when the message is ordinary or neutral. Direct any negative feeling at the situation, never at the user.',
    f.delivery,
    'Never infer, diagnose or change the user\'s emotional target. Do not invent facts. Reply in one or two short English sentences, maximum 45 words. Return only the spoken reply, without labels, JSON or stage directions.',
  ].join(' ');
  return [{role:'system',content:system},
    ...history.slice(-6).filter(m=>['user','assistant'].includes(m.role)).map(m=>({role:m.role,content:String(m.content).slice(0,800)})),{role:'user',content:text}];
}
