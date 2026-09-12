// A random code that links one browser's Listening, Test and Explore sessions for the researcher's per-listener export.
// It is not derived from the nickname.
export const LISTENER_KEY='echo-listener-v1';
export const LISTENER_PATTERN=/^L-[A-F0-9]{32}$/;
let memory=null;
const fresh=()=>'L-'+crypto.randomUUID().replaceAll('-','').toUpperCase();
export function listenerId(){
 try{const saved=localStorage.getItem(LISTENER_KEY);if(LISTENER_PATTERN.test(saved||''))return saved;const id=memory||fresh();localStorage.setItem(LISTENER_KEY,id);memory=id;return id;}
 catch{return memory||=fresh();}
}
