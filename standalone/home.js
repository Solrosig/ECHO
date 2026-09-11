import {readNickname,rememberNickname} from './participant.js';
const params=new URLSearchParams(location.search),legacy=params.get('mode');
if(['listening','line','explore'].includes(legacy)){const dest=new URL('/studio',location.origin);dest.search=location.search;location.replace(dest);}
const input=document.getElementById('entry-nickname'),error=document.getElementById('entry-error'),form=document.getElementById('entry-form');input.value=readNickname();
function remember(){try{rememberNickname(input.value);input.setCustomValidity('');error.hidden=true;return true;}catch(e){input.setCustomValidity(e.message);error.textContent=e.message;error.hidden=false;input.reportValidity();return false;}}
input.addEventListener('input',()=>{input.setCustomValidity('');error.hidden=true;});input.addEventListener('change',()=>{if(input.value.trim())remember();});
form.addEventListener('submit',e=>{e.preventDefault();remember();});
for(const a of document.querySelectorAll('[data-entry]'))a.addEventListener('click',event=>{if(!remember())event.preventDefault();});
