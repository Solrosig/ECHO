export class NeuralClient{
  constructor(createWorker=()=>new Worker(new URL('./neural.worker.js',import.meta.url),{type:'module'}),timeout=600000){this.createWorker=createWorker;this.timeout=timeout;this.serial=0;}
  run(payload,onEvent){
    if(this.pending)return Promise.reject(new Error('A model operation is already active.'));
    return new Promise((resolve,reject)=>{
      const id=++this.serial,created=!this.worker;
      const total=setTimeout(()=>this.reset(new Error('The model operation timed out. Please retry or choose another voice.')),this.timeout);
      this.pending={resolve,reject,total,id,onEvent,created};
      const idle=()=>{clearTimeout(this.pending?.idle);if(this.pending)this.pending.idle=setTimeout(()=>this.reset(new Error('No model progress for 120 seconds. Please retry or choose another voice.')),120000);};
      try{
        if(!this.worker){
          const worker=this.createWorker();this.worker=worker;
          worker.onerror=e=>{if(worker===this.worker)this.reset(new Error(e.message||'The model worker stopped.'));};
          worker.onmessageerror=()=>this.reset(new Error('The browser could not decode the model response.'));
          worker.onmessage=({data})=>{
            if(worker!==this.worker||data.id!==this.pending?.id)return;
            idle();if(data.type==='result'||data.type==='error'){
              const p=this.pending;clearTimeout(p.total);clearTimeout(p.idle);this.pending=null;
              // worker_created marks a request whose time includes starting the worker and loading its scripts.
              if(data.type==='result'){if(data.result?.timing)data.result.timing.worker_created=p.created;p.resolve(data.result);}else p.reject(new Error(data.message));
            }else this.pending.onEvent(data);
          };
        }
        idle();this.worker.postMessage({...payload,id});
      }catch(e){this.reset(e);}
    });
  }
  reset(error=new Error('Operation cancelled.')){
    this.worker?.terminate();this.worker=null;
    if(this.pending){clearTimeout(this.pending.total);clearTimeout(this.pending.idle);this.pending.reject(error);this.pending=null;}
  }
}
