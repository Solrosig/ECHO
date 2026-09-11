try{localStorage.setItem('echo-studio-exposed','1');}catch{}
for(const a of document.querySelectorAll('audio'))a.addEventListener('play',()=>{for(const b of document.querySelectorAll('audio'))if(a!==b)b.pause();});
