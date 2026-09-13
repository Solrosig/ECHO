import {readNickname,rememberNickname,validateNickname,nicknameAvailable,NICKNAME_TAKEN} from './participant.js';
import {listenerId} from './listener.js';
const params=new URLSearchParams(location.search),legacy=params.get('mode');
if(['listening','line','explore'].includes(legacy)){const dest=new URL('/studio',location.origin);dest.search=location.search;location.replace(dest);}
const input=document.getElementById('entry-nickname'),error=document.getElementById('entry-error'),form=document.getElementById('entry-form');input.value=readNickname();
function invalid(message){input.setCustomValidity(message);error.textContent=message;error.hidden=false;input.reportValidity();return false;}
// The nickname is remembered only after the server confirms that no other browser uses it.
async function claim(){let name;try{name=validateNickname(input.value);}catch(e){return invalid(e.message);}
 if(!await nicknameAvailable(name,listenerId()))return invalid(NICKNAME_TAKEN);
 rememberNickname(name);input.setCustomValidity('');error.hidden=true;return true;}
input.addEventListener('input',()=>{input.setCustomValidity('');error.hidden=true;});input.addEventListener('change',()=>{if(input.value.trim())void claim();});
form.addEventListener('submit',e=>{e.preventDefault();void claim();});
for(const a of document.querySelectorAll('[data-entry]'))a.addEventListener('click',event=>{event.preventDefault();void claim().then(ok=>{if(ok)location.assign(a.href);});});
