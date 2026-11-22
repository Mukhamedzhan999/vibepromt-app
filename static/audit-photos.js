(() => {
 'use strict';
 let catalogRequest;
 function load(){
  if(!catalogRequest)catalogRequest=fetch('/static/audit-photo-catalog.json')
   .then(response=>{if(!response.ok)throw Error('Catalog unavailable');return response.json()})
   .catch(error=>{catalogRequest=undefined;throw error});
  return catalogRequest;
 }
 const clean=(s,limit)=>typeof s==='string'?s.replace(/\s+/g,' ').trim().slice(0,limit):'';
 const fold=s=>s.toLowerCase().normalize('NFKC').replace(/[\p{P}\p{S}]+/gu,' ').replace(/\s+/g,' ').trim();
 function build(audit,catalog){
  const editorial=audit.evidence?.editorial;
  const pages=Array.isArray(editorial?.pages)?editorial.pages:[];
  const results=Array.isArray(audit.evidence?.page_results)?audit.evidence.page_results:[];
  const sourcePages=pages.some(page=>page&&typeof page==='object')?pages:results;
  const title=clean(editorial?.title,100);
  const seen=new Set();
  const rows=sourcePages.map((page,index)=>{
   if(!page||typeof page!=='object')return null;
   const number=Number.isInteger(page.page)&&page.page>0?page.page:index+1;
   const headings=Array.isArray(page.headings)?page.headings:[];
   const titleLine=clean(page.heading||headings[0],125);
   const excerpt=clean(page.source_text||page.excerpt||page.text_excerpt,2200);
   const heading=fold([titleLine,...headings.slice(0,4).map(s=>clean(s,125))].join(' '));
   const opening=fold(excerpt.slice(0,420)), detail=fold(excerpt);
   const weights=catalog.map(photo=>{
    const score=Math.max(...photo.terms.map(term=>{
     const phrase=fold(term);
     const specificity=phrase.split(' ').length;
     return heading.includes(phrase)?12+specificity*2:opening.includes(phrase)?5+specificity*2:detail.includes(phrase)?1+specificity:0;
    }));
    return {photo,score};
   }).filter(candidate=>candidate.score>=5).sort((a,b)=>b.score-a.score);
   return {number,titleLine,excerpt,weights};
  }).filter(row=>{if(!row||seen.has(row.number))return false;seen.add(row.number);return true});
  const declared=Number.isInteger(audit.pages)?audit.pages:0;
  for(let number=1;number<=Math.min(200,declared);number++){
   if(!seen.has(number))rows.push({number,titleLine:'',excerpt:'',weights:[]});
  }
  const assigned=new Map(),used=new Set();
  const choices=rows.flatMap(row=>row.weights.map(match=>({...match,number:row.number})))
   .sort((a,b)=>b.score-a.score||a.number-b.number);
  for(const {number,photo} of choices){
   if(assigned.has(number)||used.has(photo.id))continue;
   assigned.set(number,photo);used.add(photo.id);
  }
  return rows.sort((a,b)=>a.number-b.number).map(row=>({
   page:row.number,
   topic:row.titleLine||clean(row.excerpt,120)||title,
   excerpt:row.excerpt,
   asset:assigned.get(row.number)||null
  }));
 }
 function packPath(plan){
  const ids=plan.flatMap(row=>row.asset?[row.asset.id]:[]);
  return ids.length?'/api/audit-photo-pack?ids='+encodeURIComponent([...new Set(ids)].join(',')):'';
 }
 function instructions(plan){
  return plan.map(({page,topic,asset})=>'Page '+page+' — '+topic+
   (asset?': '+asset.subject+' ('+asset.credit+')':'')).join('\n');
 }
 function projectReferences(topic,catalog){
  const text=fold(topic||'');
  return catalog.filter(asset=>asset.terms.some(term=>{
   const phrase=fold(term);
   return phrase.length>=6&&text.includes(phrase);
  })).slice(0,5).map(asset=>asset.subject+' ('+asset.credit+')').join('\n');
 }
 function exportPrompt(audit,plan,catalog,language){
  const source=audit.evidence?.editorial;
  const preset=window.VibeDesignPresets.select({title:source?.title,domain:source?.domain,topic:plan.map(row=>row.topic).join(' ')});
  const palette=Object.entries(preset.palette).map(([key,value])=>key+' '+value).join(', ');
  const index=plan.map(row=>row.page+'. '+row.topic).join('\n');
  const options=catalog.map(asset=>asset.id+' — '+asset.subject).join('\n');
  return [
   'Goal\nAs a presentation editor, prepare the '+plan.length+'-page '+language+' presentation as a JSON plan for VibePrompt PDF export.',
   'Design\n'+palette+'. Pair '+preset.fonts.heading+' headings with '+preset.fonts.body+' body text and a Cyrillic Extended fallback.',
   'Content\nUse the source facts and examples to explain one point per page in natural '+language+'.\n'+index+
    '\nJSON format: {"title":"…","page_count":'+plan.length+',"pages":[{"page":1,"title":"…","body":"…","caption":"…","photo_id":"…"}]}. Field sizes: title 140, body 960, caption 400 characters.',
   'Visuals\nSelect a relevant photograph for each page and describe its connection to the text. Use a matching catalog ID in photo_id, or supply image_url and image_credit for a suitable Commons or Library of Congress photo and leave photo_id empty.\n'+options
  ].join('\n\n');
 }
 const subjects={
  'it-lab':['компьютерлік оқу сыныбы','учебный компьютерный класс','a computer classroom'],
  'daily-devices':['ноутбук пен смартфон','ноутбук и смартфон','a laptop and a smartphone'],
  processor:['компьютер процессоры','компьютерный процессор','a computer processor'],
  'software-linux':['Linux орнатылған ноутбук','ноутбук с Linux','a laptop running Linux'],
  'web-servers':['серверлік сөредегі жабдық','оборудование в серверной стойке','equipment in a server rack'],
  programming:['экранда бағдарлама коды көрсетілген ноутбук','ноутбук с кодом на экране','a laptop displaying source code'],
  'it-careers':['серверлік жабдықпен жұмыс істеп тұрған маман','специалист за работой с серверным оборудованием','a technician working with server equipment'],
  'security-key':['екі факторлы растауға арналған қауіпсіздік кілті','аппаратный ключ двухфакторной аутентификации','a hardware security key for two-factor authentication'],
  yasawi:['Қожа Ахмет Ясауи кесенесі','мавзолей Ходжи Ахмеда Ясави','the Mausoleum of Khoja Ahmed Yasawi'],
  charyn:['Шарын шатқалы','Чарынский каньон','Charyn Canyon'],
  bookshelf:['кітап сөресі','книжный стеллаж','a bookshelf']
 };
 function draft(audit,plan,language){
  const labels={
   kk:{n:0, deck:'Құжат',page:i=>i+'-бет',caption:(subject,topic)=>'Фотода '+subject+' көрсетілген. Бұл — «'+topic+'» бөліміндегі тақырыптың өмірдегі көрінісі.'},
   ru:{n:1, deck:'Документ',page:i=>'Страница '+i,caption:(subject,topic)=>'На фото — '+subject+'. Это наглядный пример к разделу «'+topic+'».'},
   en:{n:2, deck:'Document',page:i=>'Page '+i,caption:(subject,topic)=>'The photo shows '+subject+'. It illustrates the topic covered in “'+topic+'”.'}
  }[language];
  const title=clean(audit.evidence?.editorial?.title,140)||plan[0]?.topic||labels.deck;
  return {title,page_count:plan.length,pages:plan.map(row=>{
   const topic=clean(row.topic,125)||labels.page(row.page);
   const subject=subjects[row.asset?.id]?.[labels.n]||row.asset?.subject;
   const text=row.excerpt;
   const stop=text.slice(0,960).lastIndexOf('. ');
   const body=text.length<=960?text:stop>=520?text.slice(0,stop+1):clean(text,950).replace(/\s+\S*$/,'')+'…';
   return {page:row.page,title:topic,body,caption:subject?labels.caption(subject,topic):'',photo_id:row.asset?.id||''};
  })};
 }
 window.VibeAuditPhotos={load,build,packPath,instructions,projectReferences,exportPrompt,draft};
})();
