// SQLite persistence for the standalone Node server and disposable tests.
import { DatabaseSync } from 'node:sqlite';
import { readdirSync,readFileSync,mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
export function localDatabase(filename=':memory:') {
  if(filename!==':memory:')mkdirSync(dirname(filename),{recursive:true});
  const sqlite=new DatabaseSync(filename);sqlite.exec('PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000');
  sqlite.exec('CREATE TABLE IF NOT EXISTS _local_migrations (name TEXT PRIMARY KEY)');
  for(const file of readdirSync(new URL('../drizzle/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort()) {
    if(sqlite.prepare('SELECT name FROM _local_migrations WHERE name=?').get(file))continue;
    sqlite.exec('BEGIN');try{sqlite.exec(readFileSync(new URL('../drizzle/'+file,import.meta.url),'utf8'));sqlite.prepare('INSERT INTO _local_migrations VALUES (?)').run(file);sqlite.exec('COMMIT');}catch(e){sqlite.exec('ROLLBACK');throw e;}
  }
  function prepared(sql,values=[]) {
    const q=()=>sqlite.prepare(sql);
    return {bind(...args){return prepared(sql,args);},async first(){return q().get(...values) || null;},async all(){return {results:q().all(...values)};},async run(){const x=q().run(...values);return {success:true,meta:{changes:Number(x.changes)}};},execute(){return q().run(...values);}};
  }
  return {prepare:prepared,async batch(statements){sqlite.exec('BEGIN');try{const results=statements.map(s=>s.execute());sqlite.exec('COMMIT');return results;}catch(e){sqlite.exec('ROLLBACK');throw e;}},close(){sqlite.close();},sqlite};
}
