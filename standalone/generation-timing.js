// Latency data kept with each generated message (echo-generation-v2). Every time is measured in the participant's browser,
// so it describes this deployment (device, network, shared queue), not an engine's speed alone.
export const GENERATION_METADATA_VERSION='echo-generation-v2';
// Milliseconds to seconds with millisecond resolution; anything that is not a valid duration becomes null.
export const seconds=ms=>Number.isFinite(ms)&&ms>=0?Math.round(ms)/1000:null;
export const clock=()=>performance.now();

// Gradio reports the queue as 'pending' statuses and sends one more when a worker takes the request (process_starts),
// so the last pending status marks where the queue ends and work on the speech service begins.
export function queueTracker(submittedAt,now=clock){
  let lastPending=null,position=null;
  return {
    status(event){
      if(event?.stage!=='pending')return;
      lastPending=now();
      if(Number.isInteger(event.position)&&event.position>=0)position=Math.max(position??0,event.position+1);
    },
    // max_queue_position is the highest place shown to the page; 1 means next in line or started at once.
    summary(completedAt){return {queue_s:lastPending===null?null:seconds(lastPending-submittedAt),service_processing_s:lastPending===null?null:seconds(completedAt-lastPending),max_queue_position:position};}
  };
}

// Whether the page was hidden at any moment while a request ran: browsers slow background tabs.
export function visibilityWatch(doc=globalThis.document){
  if(!doc?.addEventListener)return {stop:()=>null};
  let hidden=doc.visibilityState==='hidden';
  const changed=()=>{if(doc.visibilityState==='hidden')hidden=true;};
  doc.addEventListener('visibilitychange',changed);
  return {stop(){doc.removeEventListener('visibilitychange',changed);return hidden;}};
}

// Coarse device and network classes the browser already exposes; nothing that identifies a person or a device.
export function deviceContext(nav=globalThis.navigator){
  const cores=nav?.hardwareConcurrency,memory=nav?.deviceMemory,network=nav?.connection?.effectiveType;
  return {
    hardware_concurrency:Number.isInteger(cores)&&cores>0&&cores<=1024?cores:null,
    device_memory_gb:Number.isFinite(memory)&&memory>0&&memory<=1024?memory:null,
    network_effective_type:['slow-2g','2g','3g','4g'].includes(network)?network:null
  };
}

// Columns the exploratory CSV appends for latency analysis; messages saved before echo-generation-v2 leave them empty.
export const TIMING_COLUMNS=['rating_elapsed_s','generation_metadata_version','tts_connect_s','tts_queue_s','tts_service_processing_s','tts_service_s','tts_max_queue_position','tts_download_s','tts_model_load_s','tts_synthesis_s','tts_browser_processing_s','tts_cold_start','tts_worker_created','first_request_for_engine_in_page','tts_page_hidden','reply_wait_s','reply_model_start_retries','reply_attempt_id','exchange_end_to_end_s','exchange_page_hidden','hardware_concurrency','device_memory_gb','network_effective_type'];
export function timingColumns(meta,rating){
  const t=meta?.timing||{},d=meta?.dialogue||{},x=meta?.exchange||{},c=meta?.client||{};
  return {rating_elapsed_s:rating?.elapsed_s,generation_metadata_version:meta?.version,
    tts_connect_s:t.connect_s,tts_queue_s:t.queue_s,tts_service_processing_s:t.service_processing_s,tts_service_s:t.service_s,tts_max_queue_position:t.max_queue_position,tts_download_s:t.download_s,
    tts_model_load_s:t.model_load_s,tts_synthesis_s:t.synthesis_s,tts_browser_processing_s:t.browser_processing_s,tts_cold_start:t.cold_start,tts_worker_created:t.worker_created,
    first_request_for_engine_in_page:t.first_request_for_engine_in_page,tts_page_hidden:t.page_hidden,
    reply_wait_s:d.reply_wait_s,reply_model_start_retries:d.model_start_retries,reply_attempt_id:d.attempt_id,exchange_end_to_end_s:x.end_to_end_s,exchange_page_hidden:x.page_hidden,
    hardware_concurrency:c.hardware_concurrency,device_memory_gb:c.device_memory_gb,network_effective_type:c.network_effective_type};
}

// The conversation prompt and the reply check behind each Explore message, appended after the timing columns.
export const REPLY_CHECK_COLUMNS=['reply_prompt_version','reply_check_status','reply_check_attempts','reply_check_accepted'];
export function replyCheckColumns(meta){
  const d=meta?.dialogue||{},c=d.check||{};
  return {reply_prompt_version:d.prompt_version,reply_check_status:c.status,reply_check_attempts:c.attempts,reply_check_accepted:c.accepted};
}
