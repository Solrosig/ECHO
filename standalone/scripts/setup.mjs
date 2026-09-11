import {randomBytes} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setPassword} from '../server/auth.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
try{
  if(Number(process.versions.node.split('.')[0])!==24)throw new Error('Install Node.js 24 LTS first.');
  const password=process.env.ECHO_ADMIN_PASSWORD||randomBytes(24).toString('base64url');
  setPassword(resolve(process.env.ECHO_DATA_DIR||resolve(root,'data')),password,{replace:process.argv.includes('--reset')});
  console.log('Researcher access created. Store this password privately:');console.log(password);
  console.log('The password is stored only as a salted hash. Run: node server/start.mjs');
  if(process.argv.includes('--reset'))console.log('Existing researcher sessions are invalidated. Study ratings are unchanged.');
}catch(error){console.error(error.message);process.exitCode=1;}
