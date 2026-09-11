"""Optional documentation build; uses Python standard library, not needed to run ECHO."""
from pathlib import Path
import html,re
ROOT=Path(__file__).resolve().parent.parent
STYLE='''body{font:17px/1.65 system-ui,sans-serif;color:#172438;background:#f5f7fa;margin:0}main{max-width:920px;margin:40px auto;background:white;padding:48px;border-top:5px solid #315dd1}h1{font-size:2.1rem;line-height:1.2}h2{margin-top:2.3rem;border-bottom:1px solid #ddd;padding-bottom:.4rem}h3{margin-top:1.8rem}a{color:#214fb8}pre{background:#eef2f7;padding:18px;overflow:auto;font-size:14px}code{font-family:ui-monospace,monospace;background:#eef2f7}table{border-collapse:collapse;width:100%;font-size:15px}td,th{border:1px solid #ccd4df;padding:10px;text-align:left;vertical-align:top}th{background:#eef2f7}li{margin:.4em 0}@media(max-width:700px){main{margin:0;padding:22px}h1{font-size:1.7rem}}@media print{body{background:white}main{padding:0;border:0;margin:0;max-width:none}pre,table{break-inside:avoid}}'''
def inline(s):
 s=html.escape(s)
 def link(m):
  href=html.unescape(m[2]);href=href[:-3]+'.html' if not href.startswith('http') and href.endswith('.md') else href
  return '<a href="'+html.escape(href,quote=True)+'">'+m[1]+'</a>'
 s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,s)
 s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
 return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
def render(s):
 lines=s.splitlines();out=[];i=0
 while i<len(lines):
  line=lines[i]
  if not line.strip():i+=1;continue
  if line.startswith('```'):
   block=[];i+=1
   while i<len(lines) and not lines[i].startswith('```'):block.append(lines[i]);i+=1
   out.append('<pre><code>'+html.escape('\n'.join(block))+'</code></pre>');i+=1;continue
  if line.startswith('#'):
   m=re.match(r'^(#{1,6}) (.*)',line)
   if m:level=len(m[1]);out.append(f'<h{level}>{inline(m[2])}</h{level}>');i+=1;continue
  if line.startswith('|'):
   rows=[]
   while i<len(lines) and lines[i].startswith('|'):
    row=lines[i].strip('|').split('|')
    if not all(re.fullmatch(r'\s*:?-+:?\s*',c) for c in row):rows.append(row)
    i+=1
   out.append('<table>'+''.join('<tr>'+''.join(f'<{"th" if n==0 else "td"}>{inline(c.strip())}</{"th" if n==0 else "td"}>' for c in row)+'</tr>' for n,row in enumerate(rows))+'</table>');continue
  if re.match(r'^(?:- |\d+\. )',line):
   numbered=bool(re.match(r'^\d+\.',line));tag='ol' if numbered else 'ul';start=int(line.split('.')[0]) if numbered else 1;items=[]
   while i<len(lines) and re.match(r'^(?:- |\d+\. )',lines[i]):items.append('<li>'+inline(re.sub(r'^(?:- |\d+\. )','',lines[i]))+'</li>');i+=1
   out.append((f'<ol start="{start}">' if numbered else '<ul>')+''.join(items)+f'</{tag}>');continue
  paragraph=[line];i+=1
  while i<len(lines) and lines[i].strip() and not re.match(r'^(#|```|\||- |\d+\. )',lines[i]):paragraph.append(lines[i]);i+=1
  out.append('<p>'+inline(' '.join(paragraph))+'</p>')
 return '\n'.join(out)
for src in [ROOT/'README.md',*sorted((ROOT/'docs').glob('*.md')),ROOT/'research-bundle/README.md']:
 title=src.read_text().splitlines()[0].lstrip('# ')
 doc='<!doctype html><html lang="'+('uk' if src.stem.endswith('_UA') else 'en')+'"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><main>'+render(src.read_text())+'</main></html>'
 src.with_suffix('.html').write_text(doc)
# Public help does not expose the private analysis key.
(ROOT/'public/README.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ECHO guide</title><style>'+STYLE+'</style><main><h1>Using ECHO</h1><p>Choose Listening test, Test mode or Explore Mode from the homepage. Listening compares nine systems across 27 clips per participant. Complete it before trying the named voices.</p><p>Test offers Kokoro, Chatterbox, StyleTTS2, CosyVoice2 and Parler-TTS. Explore offers Chatterbox, Parler-TTS and Kokoro, with one engine fixed for up to ten exchanges. Each voice message can be rated after playback. Use Show transcript to read a reply.</p><p>Enter a nickname and review the data information. Listening ratings and exploratory messages/ratings are saved separately in the study database. A browser backup supports retry. Remote neural speech receives your text and chosen emotion; do not enter personal information. Free hosting may queue requests or reach its GPU quota.</p><p><a href="/">Homepage</a> · <a href="/studio?mode=listening">Listening</a> · <a href="/studio?mode=line">Test</a> · <a href="/studio?mode=explore">Explore</a> · <a href="/research">Researcher access</a></p><p>The independent archive includes setup, speech-service, deployment and database-backup instructions.</p></main></html>')
print('HTML guides generated.')
