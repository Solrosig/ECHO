// Starts the local Ollama when Explore needs the conversation model and nothing answers, then loads the model, so nobody
// has to start Ollama by hand. Only `node server/start.mjs` creates a launcher; ECHO_OLLAMA_AUTOSTART=0 turns it off.
// The detached Ollama keeps running after ECHO stops, as if started from the Start menu.
import {spawn as nodeSpawn} from 'node:child_process';
import {join} from 'node:path';

export const START_RETRY_MS=60000;
export const PRELOAD_INTERVAL_MS=4*60000;

// Where the official installers put Ollama; ECHO_OLLAMA_EXE overrides it.
export function ollamaCommand(env=process.env,platform=process.platform){
  if(env.ECHO_OLLAMA_EXE)return env.ECHO_OLLAMA_EXE;
  return platform==='win32'&&env.LOCALAPPDATA?join(env.LOCALAPPDATA,'Programs','Ollama','ollama.exe'):'ollama';
}

export function createOllamaLauncher({url,model,command=ollamaCommand(),spawn=nodeSpawn,fetchImpl=fetch,now=Date.now,delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),log=console}){
  const address=new URL(url),bind=`${address.hostname}:${address.port||(address.protocol==='https:'?443:80)}`;
  let startedAt=-Infinity,preloadedAt=-Infinity,missing=false;
  const answers=async()=>{try{return (await fetchImpl(`${url}/api/version`,{signal:AbortSignal.timeout(2000)})).ok;}catch{return false;}};
  const launcher={
    get missing(){return missing;},
    // Loads the model so the first reply does not wait for it; Ollama frees the memory after its idle time (5 minutes by default).
    preload(){
      if(now()-preloadedAt<PRELOAD_INTERVAL_MS)return;
      preloadedAt=now();
      fetchImpl(`${url}/api/generate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})}).then(response=>response.text()).catch(()=>{preloadedAt=-Infinity;});
    },
    // True while a start is under way; false when Ollama cannot be started on this computer.
    start(){
      if(missing)return false;
      if(now()-startedAt<START_RETRY_MS)return true;
      startedAt=now();
      try{
        const child=spawn(command,['serve'],{detached:true,stdio:'ignore',windowsHide:true,env:{...process.env,OLLAMA_HOST:bind}});
        child.on('error',error=>{missing=true;log.error(error.code==='ENOENT'?`Ollama was not found at ${command}. Install Ollama or set ECHO_OLLAMA_EXE.`:`Ollama could not start: ${error.message}`);});
        child.unref();
      }catch(error){missing=true;log.error(`Ollama could not start: ${error.message}`);return false;}
      log.log(`Starting Ollama for Explore (${command} serve).`);
      void (async()=>{for(let i=0;i<60&&!missing;i++){if(await answers()){launcher.preload();return;}await delay(1000);}})();
      return true;
    }
  };
  return launcher;
}
