// Fixed voices and conservative engineering presets; human perception remains to be evaluated.
export const CALIBRATION_VERSION='echo-acoustic-calibration-20260907-v3';
const neutral={rate:1,gain:.8,pitch_semitones:0};
const native=()=>Object.fromEntries(["happy","upset","sad","calm"].map(e=>[e,{...neutral}]));
export const ENGINE_PROFILES={
 chatterbox:native(),zipvoice:native(),styletts2:native(),cosyvoice2:native(),parlertts:native(),
 kokoro:{happy:{rate:1.14,gain:.95,pitch_semitones:1.5},upset:{rate:1.06,gain:1.20,pitch_semitones:.5},sad:{rate:.76,gain:.48,pitch_semitones:-2.5},calm:{rate:.96,gain:.70,pitch_semitones:0}},
 piper:{happy:{rate:1.24,gain:1.00,pitch_semitones:2.25},upset:{rate:1.08,gain:1.20,pitch_semitones:.25},sad:{rate:.74,gain:.48,pitch_semitones:-2.25},calm:{rate:.96,gain:.70,pitch_semitones:0}}
};
