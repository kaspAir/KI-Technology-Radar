# radar_js.py — die clientseitige Radar-Engine (Ring-Radare / Sektor-Spalten),
# geteilt von render.py (statischer Build) UND app (MVP /radar). Erwartet die
# globalen THEMES (id,name,ring,sector,href,dom[,prov,dep]) + SECTORS im DOM,
# einen <div id="radararea"> und optional die View-Toggle-Buttons.
RADAR_JS = r"""
const GOLD='#C0851F',INK='#23262D';
const RINGORDER=['Adopt','Pilot','Explore','Watch'];
const RINGMEAN={Adopt:'produktiv nutzen',Pilot:'real erproben',Explore:'experimentieren',Watch:'beobachten'};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function curFilter(){var s=document.getElementById('bran');return s?s.value:'';}
function matches(t,f){return !f||((' '+(t.dom||'')+' ').indexOf(' '+f+' ')>=0);}
function byRingOf(list){var m={};list.forEach(function(t){(m[t.ring]=m[t.ring]||[]).push(t);});return m;}

function renderColumns(byRing){
  var h='',any=false;
  RINGORDER.forEach(function(ring){
    var ts=byRing[ring];if(!ts||!ts.length)return;any=true;
    h+='<section class="rpanel"><div class="rphead"><span class="rpname">'+ring+'</span><span class="rpmean">'+RINGMEAN[ring]+'</span><span class="rpcount">'+ts.length+'</span></div><div class="rpcols" style="--nsec:'+SECTORS.length+'">';
    SECTORS.forEach(function(sec){
      var st=ts.filter(function(t){return t.sector===sec.id;});
      h+='<div class="rpcol"><div class="rpcolh">'+esc(sec.label)+'</div>';
      st.forEach(function(t){var c='chip';if(selProv)c+=provHit(t)?' hl':' dim';h+='<a class="'+c+'" href="'+t.href+'">'+esc(t.name)+'</a>';});
      if(!st.length)h+='<div class="rpempty">–</div>';
      h+='</div>';
    });
    h+='</div></section>';
  });
  return any?h:'<p class="rpnone">Keine Themen für diese Branche.</p>';
}

function miniRadar(ts){
  var n=SECTORS.length,cx=350,R=92,minGap=17;
  var pts=[];
  SECTORS.forEach(function(sec){
    var st=ts.filter(function(t){return t.sector===sec.id;}),m=st.length,span=30;
    st.forEach(function(t,k){
      var off=m===1?0:(k-(m-1)/2)*(span/Math.max(1,m));
      var ang=(sec.angle+off)*Math.PI/180,br=R*(0.66-(k%3)*0.12);
      pts.push({t:t,cos:Math.cos(ang),br:br,right:Math.cos(ang)>=-0.0001,dy:Math.sin(ang)*br});
    });
  });
  ['right','left'].forEach(function(side){
    var isR=side==='right';
    var g=pts.filter(function(p){return p.right===isR;}).sort(function(a,b){return a.dy-b.dy;});
    g.forEach(function(p,i){p.ly=(i===0)?p.dy:Math.max(p.dy,g[i-1].ly+minGap);});
  });
  var maxAbs=60;pts.forEach(function(p){maxAbs=Math.max(maxAbs,Math.abs(p.ly),Math.abs(p.dy));});
  var H=Math.max(210,2*maxAbs+50),cy=H/2;
  var s=['<svg viewBox="0 0 700 '+H.toFixed(0)+'" class="mini" xmlns="http://www.w3.org/2000/svg">'];
  s.push('<circle cx="'+cx+'" cy="'+cy+'" r="'+R+'" fill="'+GOLD+'" fill-opacity="0.10" stroke="'+INK+'" stroke-opacity="0.18"/>');
  for(var i=0;i<n;i++){var b=(-90-(360/n)/2+i*(360/n))*Math.PI/180;s.push('<line x1="'+cx+'" y1="'+cy+'" x2="'+(cx+R*Math.cos(b)).toFixed(1)+'" y2="'+(cy+R*Math.sin(b)).toFixed(1)+'" stroke="'+INK+'" stroke-opacity="0.12"/>');}
  // Sektor-Kurzmarke (Nummer) am Rand — die Namen stehen einmal in der Legende
  // darüber. So kollidiert nichts mit den äusseren Theme-Labels.
  SECTORS.forEach(function(sec,i){var a=sec.angle*Math.PI/180;var lx=cx+(R-11)*Math.cos(a),ly=cy+(R-11)*Math.sin(a);s.push('<text x="'+lx.toFixed(0)+'" y="'+(ly+3).toFixed(0)+'" text-anchor="middle" font-size="10" fill="'+INK+'" fill-opacity="0.4" font-weight="600">'+(i+1)+'</text>');});
  s.push('<circle cx="'+cx+'" cy="'+cy+'" r="2.5" fill="'+INK+'" fill-opacity="0.5"/>');
  pts.forEach(function(p){
    var bx=cx+p.br*p.cos,by=cy+p.dy,lx=p.right?(cx+R+14):(cx-R-14),ly=cy+p.ly,el=p.right?(cx+R+6):(cx-R-6);
    var hit=provHit(p.t), op=selProv?(hit?'1':'0.25'):'1', col=hit?'#C0362C':GOLD, fw=hit?'700':'500', rr=hit?'6':'4.5';
    s.push('<a href="'+p.t.href+'" class="mblip" style="opacity:'+op+'"><polyline points="'+bx.toFixed(1)+','+by.toFixed(1)+' '+el.toFixed(1)+','+ly.toFixed(1)+' '+lx.toFixed(1)+','+ly.toFixed(1)+'" fill="none" stroke="'+INK+'" stroke-opacity="0.22"/><circle cx="'+bx.toFixed(1)+'" cy="'+by.toFixed(1)+'" r="'+rr+'" fill="'+col+'"/><text x="'+lx.toFixed(1)+'" y="'+(ly+3).toFixed(1)+'" text-anchor="'+(p.right?'start':'end')+'" font-size="11" font-weight="'+fw+'" fill="'+INK+'">'+esc(p.t.name)+'</text></a>');
  });
  s.push('</svg>');return s.join('');
}

function renderRadar(byRing){
  var leg='<p class="seclegend">Sektoren (Ziffern im Radar, im Uhrzeigersinn ab oben): '+SECTORS.map(function(s,i){return '<b>'+(i+1)+'</b> '+esc(s.label);}).join(' · ')+'</p>';
  var h='',any=false;
  RINGORDER.forEach(function(ring){
    var ts=byRing[ring];if(!ts||!ts.length)return;any=true;
    h+='<section class="rpanel"><div class="rphead"><span class="rpname">'+ring+'</span><span class="rpmean">'+RINGMEAN[ring]+'</span><span class="rpcount">'+ts.length+'</span></div>'+miniRadar(ts)+leg+'</section>';
  });
  return any?h:'<p class="rpnone">Keine Themen für diese Branche.</p>';
}

var selProv='';
var PLABEL={openai:'OpenAI',anthropic:'Anthropic',google:'Google',microsoft:'Microsoft',meta:'Meta',deepseek:'DeepSeek',nvidia:'Nvidia',open:'Offen (Hedge)'};
function provHit(t){return !!(selProv&&((' '+(t.prov||'')+' ').indexOf(' '+selProv+' ')>=0));}
function renderRadarArea(){
  var f=curFilter(),mode=localStorage.getItem('radarview')||'radar';
  selProv=(document.getElementById('prov')||{}).value||'';
  var vis=THEMES.filter(function(t){return matches(t,f);});
  var byRing=byRingOf(vis);
  var el=document.getElementById('radararea');
  if(!el)return;
  var banner='';
  if(selProv){var n=vis.filter(provHit).length;
    banner='<p class="provnote">Wenn <b>'+(PLABEL[selProv]||selProv)+'</b> wackelt: <b>'+n+'</b> '+(n===1?'Thema':'Themen')+' betroffen (hervorgehoben). Offene/lokale Modelle sind der Hedge.</p>';}
  el.innerHTML=banner+((mode==='columns')?renderColumns(byRing):renderRadar(byRing));
  document.querySelectorAll('.vbtn').forEach(function(b){b.className='vbtn'+(b.getAttribute('data-v')===mode?' on':'');});
}
function setView(m){localStorage.setItem('radarview',m);renderRadarArea();}
function branf(){
  var v=curFilter();
  document.querySelectorAll('.cardlink').forEach(function(el){
    el.style.display=(!v||((' '+(el.getAttribute('data-dom')||'')+' ').indexOf(' '+v+' ')>=0))?'':'none';
  });
  renderRadarArea();
}
document.addEventListener('DOMContentLoaded',renderRadarArea);
"""
