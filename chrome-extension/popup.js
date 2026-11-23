'use strict';

function measurePage() {
 const nodes = Array.from(document.querySelectorAll('body *')).slice(0, 12000)
  .filter(element => {
   const style = getComputedStyle(element);
   return element.getClientRects().length && style.visibility === 'visible' && style.opacity !== '0';
  });
 const count = selector => nodes.filter(element => element.matches(selector)).length;
 const hasLabel = element => Boolean(
  element.getAttribute('aria-label')?.trim() || element.getAttribute('aria-labelledby') ||
  element.labels?.length || element.textContent.trim() || element.getAttribute('title') ||
  element.querySelector('img[alt]:not([alt=""])')
 );
 const missing = selector => nodes.filter(element => element.matches(selector) && !hasLabel(element)).length;
 const controls = 'button,[role="button"]';
 const fields = 'input:not([type="hidden"]),textarea,select';
 const colors = new Set();
 const contrasts = [];
 function rgb(value) {
  const match = value.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);
  return match?.slice(1).map(Number);
 }
 const hex = triplet => '#' + triplet.map(value => value.toString(16).padStart(2,'0')).join('');
 const luminance = triplet => triplet.map(value => value / 255)
  .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
  .reduce((sum,value,index) => sum + value * [.2126,.7152,.0722][index],0);
 for (const element of nodes.filter(node => node.matches('p,h1,h2,h3,label,button,a')).slice(0,120)) {
  const style = getComputedStyle(element);
  const foreground = rgb(style.color);
  let background;
  for (let parent = element; parent; parent = parent.parentElement) {
   const surface = getComputedStyle(parent);
   if (surface.backgroundImage !== 'none') break;
   background = rgb(surface.backgroundColor);
   if (background || surface.backgroundColor !== 'rgba(0, 0, 0, 0)') break;
  }
  if (!foreground || !background) continue;
  const [first,second] = [luminance(foreground),luminance(background)].sort((a,b)=>b-a);
  const size = parseFloat(style.fontSize);
  const threshold = size >= 24 || (size >= 18.67 && Number(style.fontWeight) >= 700) ? 3 : 4.5;
  colors.add(hex(foreground));
  colors.add(hex(background));
  contrasts.push({ratio:(first+.05)/(second+.05),threshold,fg:hex(foreground),bg:hex(background)});
 }
 const cells = new Set();
 for (const element of nodes.filter(node => node.matches('p,h1,h2,h3,img,button,input,textarea,select')).slice(0,500)) {
  const rect = element.getBoundingClientRect();
  const left = Math.max(0,Math.floor(rect.left / innerWidth * 24));
  const right = Math.min(24,Math.ceil(rect.right / innerWidth * 24));
  const top = Math.max(0,Math.floor(rect.top / innerHeight * 16));
  const bottom = Math.min(16,Math.ceil(rect.bottom / innerHeight * 16));
  for(let y=top;y<bottom;y++) for(let x=left;x<right;x++) cells.add(y*24+x);
 }
 return {
  words:Math.min(200000, document.body.innerText.trim().split(/\s+/u).filter(Boolean).length),nodes:nodes.length,
  h1:count('h1'),h2:count('h2'),images:count('img'),alt_missing:count('img:not([alt])'),
  controls:count(controls),nameless_controls:missing(controls),links:count('a[href]'),nameless_links:missing('a[href]'),
  fields:count(fields),unlabelled_fields:missing(fields),iframes:count('iframe'),
  fonts:new Set(nodes.slice(0,1000).map(element=>getComputedStyle(element).fontFamily)).size,
  whitespace:Math.round(100*(1-cells.size/384)),contrasts,colors:[...colors].slice(0,6),
  title:Boolean(document.title),language:Boolean(document.documentElement.lang),viewport:Boolean(document.querySelector('meta[name=viewport]'))
 };
}

const capture = document.querySelector('#capture');
const ready = document.querySelector('#ready');
const copy = document.querySelector('#copy');
const copyLabel = document.querySelector('#copy-label');
const copyHint = document.querySelector('#copy-hint');
const status = document.querySelector('#status');
let auditCode = '';

function showStatus(message, kind = '') {
 status.textContent=message;
 status.dataset.kind=kind;
}

function setCopied(copied) {
 const label=copied?'Код көшірілді':'Аудит кодын көшіру';
 copy.dataset.copied=String(copied);
 copy.setAttribute('aria-label',label);
 copy.title=label;
 copyLabel.textContent=copied?'Код көшірілді':'Код дайын';
 copyHint.textContent=copied?'Оны VibePrompt AI-дағы Chrome аудитіне қойыңыз.':'Кодты көшіріп алыңыз.';
}

capture.addEventListener('click',async()=>{
 capture.disabled=true;
 auditCode='';
 ready.hidden=true;
 setCopied(false);
 showStatus('Интерфейс өлшеніп жатыр…');
 try {
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const url=new URL(tab?.url);
  if (!['http:','https:'].includes(url.protocol)) throw Error();
  const [snapshot]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:measurePage});
  if (!snapshot?.result) throw Error();
  auditCode='VPA1.'+btoa(JSON.stringify({url:url.origin,result:snapshot.result}));
  ready.hidden=false;
  showStatus('Аудит коды дайын.');
 } catch {
  showStatus('Бұл бетті өлшеу мүмкін болмады. Кәдімгі сайтты ашып, қайта көріңіз.','error');
 } finally {capture.disabled=false}
});
copy.addEventListener('click',async()=>{
 if(!auditCode)return;
 const currentCode=auditCode;
 try {
  await navigator.clipboard.writeText(currentCode);
  if(auditCode!==currentCode)return;
  setCopied(true);
  showStatus('');
 } catch {
  if(auditCode!==currentCode)return;
  setCopied(false);
  showStatus('Код көшірілмеді. Көшіру белгісін қайта басыңыз.','error');
 }
});
