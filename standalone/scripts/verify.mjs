import {createReadStream,readFileSync,existsSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
async function hash(file){const h=createHash('sha256');for await(const chunk of createReadStream(file))h.update(chunk);return h.digest('hex');}
try{
 let checked=0;
 const release=JSON.parse(readFileSync(join(root,'release-manifest.json'),'utf8'));
 for(const f of release.files){const path=resolve(root,f.path);if(!path.startsWith(root)||!existsSync(path)||statSync(path).size!==f.size||await hash(path)!==f.sha256)throw new Error(`Missing or changed release file: ${f.path}`);checked++;}
 const manifest=JSON.parse(readFileSync(join(root,'public/study/manifest.json'),'utf8'));
 if(manifest.items.length!==45 || manifest.trials_per_session!==45 || manifest.study_version!=='echo-user-voice-20260910-nine-v5')throw new Error('The current frozen study must assign all 45 clips per session (v5).');
 for(const item of manifest.items)if(await hash(join(root,'public',item.audio))!==item.sha256)throw new Error(`Changed stimulus: ${item.item_id}`);
 const qwen=JSON.parse(readFileSync(join(root,'public/models/qwen/ndarray-cache.json'),'utf8'));
 for(const shard of qwen.records)if(statSync(join(root,'public/models/qwen',shard.dataPath)).size!==shard.nbytes)throw new Error(`Incomplete language-model shard: ${shard.dataPath}`);
 console.log(`PASS: ${checked} release files, 45 frozen WAVs and ${qwen.records.length} LLM shards. No network was used.`);
 console.log('A changed source file after your own edits is expected; rebuild and create a new release manifest before redistribution.');
}catch(error){console.error(error.message);process.exitCode=1;}
