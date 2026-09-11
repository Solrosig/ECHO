// Maintainer command: records a clean distribution, never runtime credentials or responses.
import {readdirSync,statSync,createReadStream,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const excluded=new Set(['node_modules','.git','.local','.DS_Store','release-manifest.json','__pycache__','.venv','.tts-venv']);
const files=[];
async function walk(dir){for(const name of readdirSync(dir).sort()){
 const path=join(dir,name),rel=relative(root,path).replaceAll('\\','/');
 if(rel==='data'||rel==='backups'||rel.startsWith('tts-service/backend/')||rel==='tts-service/backend'||excluded.has(name)||name.endsWith('.pyc')||name.startsWith('.env')&&!name.endsWith('.example')||rel.startsWith('research-bundle/analysis')||rel.startsWith('research-bundle/responses/')&&name!=='.gitkeep')continue;
 if(statSync(path).isDirectory()){await walk(path);continue;}
 const hash=createHash('sha256');for await(const c of createReadStream(path))hash.update(c);files.push({path:rel,size:statSync(path).size,sha256:hash.digest('hex')});
}}
await walk(root);writeFileSync(join(root,'release-manifest.json'),JSON.stringify({release:'echo-standalone-1.5.0',created_utc:new Date().toISOString(),files},null,2)+'\n');console.log(`Manifest contains ${files.length} distribution files.`);
