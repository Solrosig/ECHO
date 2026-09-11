import {SoundTouch} from './vendor/soundtouch/core/index.js';
import {audioResult} from './audio-utils.js';

export const PROSODY_VERSION='echo-acoustic-calibration-20260907-v3';
// Relative-gated 20 ms RMS: an engineering level reference, not LUFS or perceived loudness.
export function activeRms(samples,sampleRate){
 const n=Math.max(1,Math.round(sampleRate*.02)),frames=[];let max=0;
 for(let i=0;i<samples.length;i+=n){let sum=0;const length=Math.min(n,samples.length-i);for(let j=0;j<length;j++){const x=samples[i+j];if(!Number.isFinite(x))throw new Error('Invalid speech sample.');sum+=x*x;}const power=sum/length;frames.push([power,length]);max=Math.max(max,power);}
 if(max<1e-12)throw new Error('The speech signal is silent.');
 let energy=0,count=0;for(const [power,length] of frames)if(power>=max*.01){energy+=power*length;count+=length;}
 return Math.sqrt(energy/count);
}
export function shiftPitch(samples,sampleRate,semitones){
 if(!Number.isFinite(semitones)||Math.abs(semitones)>4)throw new Error('Pitch shift must stay within four semitones.');
 if(Math.abs(semitones)<1e-9)return samples.slice();
 const st=new SoundTouch({sampleRate,interpolationStrategy:{id:'lanczos',params:{zeroCrossings:4,normalize:true}}});
 st.pitchSemitones=semitones;st.setStretchParameters({quickSeek:false,overlapMs:12,sequenceMs:60,seekWindowMs:20});
 // Feed a short silent tail to flush the finite WSOLA windows; retain the requested duration.
 const pad=Math.ceil(sampleRate*.4),mono=new Float32Array(samples.length),block=2048;let written=0;
 for(let at=0;at<samples.length+pad;at+=block){const n=Math.min(block,samples.length+pad-at),stereo=new Float32Array(n*2);for(let i=0;i<n;i++)stereo[i*2]=stereo[i*2+1]=samples[at+i]||0;
  st.inputBuffer.putSamples(stereo);st.process();const count=st.outputBuffer.frameCount;if(count){const output=new Float32Array(count*2);st.outputBuffer.extract(output,0,count);st.outputBuffer.receive(count);for(let i=0;i<count&&written<mono.length;i++)mono[written++]=output[i*2];}
 }
 if(written<samples.length)throw new Error('The pitch processor returned incomplete speech.');
 st.clear();return mono;
}
export function calibratedAudio(samples,sampleRate,params){
 if(!Number.isFinite(sampleRate)||sampleRate<8000||sampleRate>96000||!samples.length)throw new Error('Invalid speech audio.');
 activeRms(samples,sampleRate);if(!Number.isFinite(params.gain)||params.gain<=0||params.gain>1.3)throw new Error('Invalid output gain.');
 const pitch=params.pitch_semitones||0,shifted=shiftPitch(samples,sampleRate,pitch),rms=activeRms(shifted,sampleRate);
 const requestedScale=.075/rms*params.gain;let peak=0;for(const x of shifted)peak=Math.max(peak,Math.abs(x));
 // One transparent utterance-level attenuation, never a hard clip or dynamic compressor.
 const scale=Math.min(requestedScale,.95/Math.max(peak,1e-12)),normalised=new Float32Array(shifted.length);
 for(let i=0;i<shifted.length;i++)normalised[i]=shifted[i]*scale;
 return {...audioResult(normalised,sampleRate,1),processing_version:PROSODY_VERSION,pitch_processing:pitch?'SoundTouchJS 2.1.1 WSOLA + Lanczos; formants are not preserved':'none',pitch_shift_semitones:pitch,level_reference:'20 ms RMS, relative gate -20 dB below strongest frame; reference 0.075 full scale before gain',active_rms_dbfs:20*Math.log10(activeRms(normalised,sampleRate)),level_scale:scale,headroom_attenuation_db:20*Math.log10(scale/requestedScale)};
}
