import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {localDatabase} from '../server/local-db.js';
test('migration preserves previous ratings and permits trial 45 while rejecting 46',()=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-migrate-'));const file=join(dir,'old.sqlite');let db;
 try{
  const old=new DatabaseSync(file);old.exec('PRAGMA foreign_keys=ON; CREATE TABLE _local_migrations(name TEXT PRIMARY KEY)');
  for(const name of readdirSync(new URL('../drizzle/',import.meta.url)).filter(n=>n.endsWith('.sql')&&!n.startsWith('0007')).sort()){
   old.exec(readFileSync(new URL('../drizzle/'+name,import.meta.url),'utf8'));old.prepare('INSERT INTO _local_migrations VALUES (?)').run(name);
  }
  old.exec(`INSERT INTO study_sessions(participant_id,token_hash,study_version,collection_version,record_type,group_number,seed,comfortable_english,headphones,previously_used_studio,consent_utc,received_utc,updated_utc) VALUES ('TEST-ABCD1234','fixture','old','old','technical_test',1,42,0,0,0,'2026-09-10','2026-09-10','2026-09-10');
  INSERT INTO study_responses(participant_id,trial_order,item_id,block_id,valence,arousal,naturalness,target_match,play_count,completed_audio,elapsed_s,created_utc,received_utc) VALUES ('TEST-ABCD1234',1,'fixture-waveform','fixture-block',0.2,-0.4,4,3.5,1,1,10,'2026-09-10','2026-09-10')`);
  old.close();db=localDatabase(file);
  const before=db.sqlite.prepare('SELECT * FROM study_responses').get();assert.equal(before.target_match,3.5);assert.equal(before.trial_order,1);assert.equal(before.valence,.2);
  db.sqlite.exec("UPDATE study_responses SET trial_order=45");assert.throws(()=>db.sqlite.exec("UPDATE study_responses SET trial_order=46"),/CHECK constraint failed/);
  assert.deepEqual(db.sqlite.prepare('PRAGMA foreign_key_check').all(),[]);
 }finally{db?.close();rmSync(dir,{recursive:true,force:true});}
});
