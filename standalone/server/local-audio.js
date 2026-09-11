// Node-only equivalent of the private R2 binding; generated audio never enters public/.
import {mkdir,writeFile,readFile,rename,unlink} from 'node:fs/promises';
import {resolve,dirname,sep} from 'node:path';
export function localAudio(root){
 const base=resolve(root);const path=key=>{if(!/^interactive\/X-[A-F0-9]{32}\/[0-9]+-[a-f0-9]{64}\.wav$/.test(key))throw new Error('Invalid audio key.');const p=resolve(base,key);if(!p.startsWith(base+sep))throw new Error('Invalid audio path.');return p;};
 return {async put(key,value){const p=path(key),temp=p+'.'+crypto.randomUUID()+'.tmp';await mkdir(dirname(p),{recursive:true,mode:0o700});await writeFile(temp,new Uint8Array(value),{mode:0o600});await rename(temp,p);},async get(key){try{return {body:await readFile(path(key))};}catch(e){if(e.code==='ENOENT')return null;throw e;}},async delete(key){try{await unlink(path(key));}catch(e){if(e.code!=='ENOENT')throw e;}}};
}
