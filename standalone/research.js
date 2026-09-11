const $=id=>document.getElementById(id);
function cell(row,value){const td=document.createElement('td');td.textContent=String(value);row.append(td);return td;}
async function refresh(){
 $('research-error').hidden=true;$('research-status').textContent='Loading saved responses…';
 try{
  const response=await fetch('/api/research/summary',{cache:'no-store'}),data=await response.json();
  if(response.status===401){$('research-signin').hidden=false;$('research-data').hidden=true;$('research-status').textContent='Sign in to view responses.';return;}
  if(!response.ok)throw new Error(data.error || 'Could not load results.');
  $('research-signin').hidden=true;$('research-data').hidden=false;
  const human=data.groups.filter(g=>g.record_type==='human_response'),technical=data.groups.filter(g=>g.record_type==='technical_test');
  const sum=(rows,key)=>rows.reduce((n,r)=>n+Number(r[key] || 0),0);
  for(const [id,key] of [['started','started'],['complete','completed'],['eligible','eligible'],['ratings','responses']])$('count-'+id).textContent=sum(human,key);
  $('group-rows').replaceChildren();
  for(let i=1;i<=16;i++){
   const g=human.find(g=>g.group_number===i)||{},row=document.createElement('tr');
   [i,g.started||0,g.completed||0,`${g.eligible||0} / 2`].forEach(x=>cell(row,x));
   const link=document.createElement('a');link.href=`/listen.html?g=${i}`;link.textContent=`Open group ${i}`;cell(row,'').append(link);$('group-rows').append(row);
  }
  $('session-rows').replaceChildren();
  for(const s of data.sessions){const row=document.createElement('tr');[s.nickname||'Legacy session',s.participant_id,s.study_version||'',s.record_type==='human_response'?'Human':'Technical',s.group_number,`${s.saved_count} / ${s.trials_per_session}`,s.previously_used_studio?'Yes':'No',s.updated_utc.replace('T',' ').replace('Z','')].forEach(x=>cell(row,x));$('session-rows').append(row);}
  if(!data.sessions.length){const row=document.createElement('tr'),td=cell(row,'No sessions received yet.');td.colSpan=8;$('session-rows').append(row);}
  $('technical-count').textContent=`${sum(technical,'started')} technical sessions · ${sum(technical,'completed')} complete · ${sum(technical,'responses')} clip ratings. Excluded from human results.`;
  await refreshExploration();
  $('research-status').textContent=`Updated ${new Date().toLocaleTimeString()} · ${data.study_version}`;
 }catch(error){$('research-error').textContent=error.message;$('research-error').hidden=false;$('research-status').textContent='Results could not be refreshed.';}
}
$('refresh-results').addEventListener('click',refresh);void refresh();

$('research-login').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
 try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('research-password').value})});const data=await response.json();if(!response.ok)throw new Error(data.error);$('research-password').value='';await refresh();}
 catch(error){$('research-error').textContent=error.message;$('research-error').hidden=false;}
 finally{button.disabled=false;}
});
$('research-logout').addEventListener('click',async()=>{
 try{const response=await fetch('/api/auth/logout',{method:'POST'});if(!response.ok)throw new Error('Sign out failed. Please retry.');await refresh();}
 catch(error){$('research-error').textContent=error.message;$('research-error').hidden=false;}
});

async function refreshExploration(){
 const response=await fetch('/api/research/interactive',{cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not load exploration records.');$('interactive-rows').replaceChildren();for(const s of data.sessions){const row=document.createElement('tr');[s.nickname,s.mode,s.engine||'Multiple engines',s.record_type,`${s.saved_count} messages / ${s.rated_count} ratings / ${s.archived_count||0} WAVs`,s.session_id].forEach(v=>cell(row,v));$('interactive-rows').append(row);}if(!data.sessions.length){const row=document.createElement('tr');cell(row,'No exploratory sessions received yet.').colSpan=6;$('interactive-rows').append(row);}
}
