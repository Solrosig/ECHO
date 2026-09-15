import {readNickname,rememberNickname,validateNickname,nicknameAvailable,NICKNAME_TAKEN,rememberGender,fillGender} from './participant.js';
import {listenerId} from './listener.js';
const params=new URLSearchParams(location.search),legacy=params.get('mode');
if(['listening','line','explore'].includes(legacy)){const dest=new URL('/studio',location.origin);dest.search=location.search;location.replace(dest);}
const input=document.getElementById('entry-nickname'),error=document.getElementById('entry-error'),form=document.getElementById('entry-form'),genders=[...form.querySelectorAll('input[name=gender]')];input.value=readNickname();fillGender(form);
function invalid(message,control=input){control.setCustomValidity(message);error.textContent=message;error.hidden=false;control.reportValidity();return false;}
// The nickname is remembered only after the server confirms that no other browser uses it.
async function claimNickname(){let name;try{name=validateNickname(input.value);}catch(e){return invalid(e.message);}
 if(!await nicknameAvailable(name,listenerId()))return invalid(NICKNAME_TAKEN);
 rememberNickname(name);input.setCustomValidity('');error.hidden=true;return true;}
// An activity opens only with a nickname and a gender choice; the choice is remembered like the nickname.
async function claim(){if(!await claimNickname())return false;try{rememberGender(form.elements.gender.value);}catch(e){return invalid(e.message,genders[0]);}genders[0].setCustomValidity('');error.hidden=true;return true;}
input.addEventListener('input',()=>{input.setCustomValidity('');error.hidden=true;});input.addEventListener('change',()=>{if(input.value.trim())void claimNickname();});
for(const g of genders)g.addEventListener('change',()=>{genders[0].setCustomValidity('');error.hidden=true;rememberGender(g.value);});
form.addEventListener('submit',e=>{e.preventDefault();void claim();});
for(const a of document.querySelectorAll('[data-entry]'))a.addEventListener('click',event=>{event.preventDefault();void claim().then(ok=>{if(ok)location.assign(a.href);});});
