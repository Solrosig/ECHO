import {EMOTIONS} from './voice-controls.js';

// Page names for the four targets on Russell's circumplex: quadrant, name and a valence/arousal description.
// The frozen presets in voice-controls.js keep their own ids, names and coordinates; tts-service numbers its
// reference recordings with the same quadrants.
export const QUADRANTS={
  happy:{quadrant:'Q1',name:'Happy',description:'Positive · intense'},
  upset:{quadrant:'Q2',name:'Angry',description:'Negative · intense'},
  sad:{quadrant:'Q3',name:'Sad',description:'Negative · calm'},
  calm:{quadrant:'Q4',name:'Relaxed',description:'Positive · calm'},
};

// Listening targets keep the frozen manifest's names, so the page names each one after the quadrant of its coordinates.
export function targetName(target){
  const id=Object.keys(QUADRANTS).find(key=>Math.sign(EMOTIONS[key].v)===Math.sign(target.valence)&&Math.sign(EMOTIONS[key].a)===Math.sign(target.arousal));
  return id?QUADRANTS[id].name:target.name;
}
