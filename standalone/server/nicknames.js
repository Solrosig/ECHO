import {NICKNAME_TAKEN} from '../participant.js';
export {NICKNAME_TAKEN};
// A nickname belongs to the browsers (listener codes) already using it: another browser cannot start a new session with
// it, while the same browser keeps it across Listening, Test Mode and Explore. Withdrawn and technical-test sessions, and
// sessions saved before listener codes existed, reserve nothing. The comparison ignores ASCII case.
export async function nicknameTaken(db,nickname,listenerId){
 const rows=(await db.prepare(`SELECT listener_id FROM study_sessions WHERE lower(nickname)=lower(?) AND withdrawn_utc IS NULL AND record_type<>'technical_test' AND listener_id IS NOT NULL
  UNION SELECT listener_id FROM interactive_sessions WHERE lower(nickname)=lower(?) AND withdrawn_utc IS NULL AND record_type<>'technical_test' AND listener_id IS NOT NULL`).bind(nickname,nickname).all()).results;
 const codes=new Set(rows.map(r=>r.listener_id));
 return codes.size>0&&!codes.has(listenerId);
}
