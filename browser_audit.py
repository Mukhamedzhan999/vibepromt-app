"""Rendered URL audit in a throwaway Chromium process.

All document/subresource HTTP(S) traffic is fetched through an IP-pinning gate and
fulfilled into the browser. It is a local best-effort guard, not an OS sandbox.
Use network/container isolation before exposing this to untrusted users.
"""
import sys, os, re, json, time, socket, ipaddress, subprocess, signal, shutil, base64
from urllib.parse import urlsplit, urljoin, quote
from collections import Counter
import requests, urllib3

MAX_SECONDS=65
MAX_REQUESTS=160
MAX_BYTES=60_000_000
MAX_RESOURCE=12_000_000


def _public_get(url, deadline, max_bytes, request_headers=None):
    """Fetch only public addresses; pin the connection and revalidate redirects."""
    for _ in range(5):
        if time.monotonic()>deadline: raise ValueError('Жүктеу уақыты аяқталды.')
        u=urlsplit(url)
        try: port=u.port or (443 if u.scheme=='https' else 80)
        except ValueError: raise ValueError('Порт жарамсыз.')
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or port not in (80,443):
            raise ValueError('Сілтеме қауіпсіздік талабына сай емес.')
        try:
            addrs=list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(u.hostname,port,type=socket.SOCK_STREAM)))
        except OSError: raise ValueError('Домен табылмады.')
        try:
            if not addrs or any(not ipaddress.ip_address(x).is_global for x in addrs): raise ValueError()
        except ValueError: raise ValueError('Жеке желіге кіруге тыйым салынған.')
        # Each address is validated above and used directly, preventing a second DNS lookup.
        addrs=sorted(addrs,key=lambda x:ipaddress.ip_address(x).version)[:4]
        path=quote(u.path or '/',safe="/%:@!$&'()*+,;=-._~")+('?' + quote(u.query,safe="/%:@!$&'()*+,;=?-._~") if u.query else '')
        host=u.hostname.encode('idna').decode('ascii')
        if ':' in host: host='['+host+']'
        headers_out={'Host':host,'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36','Accept':'*/*','Accept-Encoding':'gzip, deflate'}
        for key,value in (request_headers or {}).items():
            if key.lower() not in ('user-agent','accept','accept-language','referer','origin') or not isinstance(value,str) or len(value)>=2048 or '\n' in value or '\r' in value: continue
            if key.lower() in ('origin','referer'):
                parsed=urlsplit(value)
                if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password: continue
                hostpart=parsed.hostname.encode('idna').decode('ascii')
                if ':' in hostpart: hostpart='['+hostpart+']'
                value=parsed.scheme+'://'+hostpart+((':'+str(parsed.port)) if parsed.port else '')+('/' if key.lower()=='referer' else '')
            canonical={'user-agent':'User-Agent','accept':'Accept','accept-language':'Accept-Language','referer':'Referer','origin':'Origin'}
            headers_out[canonical[key.lower()]]=value
        redirected=None
        for addr in addrs:
            if time.monotonic()>deadline: raise ValueError('Жүктеу уақыты аяқталды.')
            timeout=urllib3.Timeout(connect=2.5,read=3.5)
            if u.scheme=='https':
                pool=urllib3.HTTPSConnectionPool(addr,port=port,timeout=timeout,retries=False,cert_reqs='CERT_REQUIRED',ca_certs=requests.certs.where(),assert_hostname=u.hostname,server_hostname=u.hostname)
            else: pool=urllib3.HTTPConnectionPool(addr,port=port,timeout=timeout,retries=False)
            response=None
            try:
                response=pool.request('GET',path,headers=headers_out,redirect=False,preload_content=False)
                if response.status in (301,302,303,307,308):
                    location=response.headers.get('Location')
                    if not location: raise ValueError('Қайта бағыттау мекенжайы жоқ.')
                    redirected=urljoin(url,location); break
                if response.status not in (200,204): raise ValueError('Сайт HTTP %s жауабын қайтарды.' % response.status)
                chunks=[]; total=0
                for chunk in response.stream(65536,decode_content=True):
                    total+=len(chunk)
                    if total>max_bytes: raise ValueError('Ресурс көлемі шектен асты.')
                    if time.monotonic()>deadline: raise ValueError('Жүктеу уақыты аяқталды.')
                    chunks.append(chunk)
                headers={k:response.headers[k] for k in ('Content-Type','Access-Control-Allow-Origin','Access-Control-Allow-Credentials','Access-Control-Expose-Headers','Content-Security-Policy','X-Content-Type-Options','Cross-Origin-Resource-Policy','X-Frame-Options','Referrer-Policy') if k in response.headers}
                headers['_vibe_status']=str(response.status)
                return b''.join(chunks),url,headers
            except (urllib3.exceptions.HTTPError,OSError):
                continue
            finally:
                if response is not None: response.close()
                pool.close()
        if redirected:
            url=redirected; continue
        raise ValueError('Сайтқа қосылу мүмкін болмады немесе күту уақыты аяқталды.')
    raise ValueError('Қайта бағыттау саны шектен асты.')


JS=r'''() => {
 const visible = e => { let s=getComputedStyle(e),r=e.getBoundingClientRect(); return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>0&&r.width>0&&r.height>0; };
 const all=Array.from(document.querySelectorAll('body *')); let truncated=all.length>12000;
 const nodes=all.slice(0,12000).filter(visible), q=sel=>nodes.filter(e=>e.matches(sel));
 const clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const name=e=>clean(e.getAttribute('aria-label')||e.getAttribute('title')||e.value||e.innerText||e.textContent||Array.from(e.querySelectorAll('img[alt]')).map(x=>x.getAttribute('alt')).join(' ')||((e.getAttribute('aria-labelledby')||'').split(/\s+/).map(x=>document.getElementById(x)?.innerText||'').join(' ')));
 const text=clean(document.body?.innerText||''); const words=text?text.split(/\s+/).length:0;
 const heads=q('h1'), h2=q('h2'), images=q('img'), controls=q('button,input[type=submit],input[type=button],[role=button]'), links=q('a[href]');
 const fields=q('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea');
 const labeled=e=>!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')||e.closest('label')||(e.id&&Array.from(document.querySelectorAll('label[for]')).some(l=>l.htmlFor===e.id)));
 const fonts=new Set(), colors={}, contrasts=[];
 const rgba=s=>{let m=s.match(/^rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)(?:\s*,\s*(\d+(?:\.\d+)?))?\s*\)$/);return m?[+m[1],+m[2],+m[3],m[4]===undefined?1:+m[4]]:null};
 const hex=c=>'#'+c.slice(0,3).map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');
 const lum=c=>c.slice(0,3).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
 for (const el of nodes) {
  const cs=getComputedStyle(el); if(clean(el.innerText||el.textContent).length){fonts.add(cs.fontFamily+' / '+cs.fontSize); let fg=rgba(cs.color);if(fg&&fg[3]===1)colors[hex(fg)]=(colors[hex(fg)]||0)+1;}
  if(contrasts.length>=400 || !el.childNodes.length || !Array.from(el.childNodes).some(n=>n.nodeType===3&&clean(n.nodeValue).length>1))continue;
  // Only opaque text over an opaque, image-free background, with no partial opacity.
  let fg=rgba(cs.color), bg=null, okay=fg&&fg[3]===1, cur=el;
  while(cur&&okay){let st=getComputedStyle(cur); if(Number(st.opacity)<1||st.backgroundImage!=='none'){okay=false;break}let b=rgba(st.backgroundColor);if(b&&b[3]>0&&b[3]<1){okay=false;break}if(b&&b[3]===1){bg=b;break}cur=cur.parentElement;}
  if(!okay||!bg)continue;
  let a=lum(fg),b=lum(bg), ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  let size=parseFloat(cs.fontSize),bold=parseInt(cs.fontWeight,10)>=700, threshold=size>=24||(size>=18.66&&bold)?3:4.5;
  let r=el.getBoundingClientRect(); contrasts.push({ratio:Math.round(ratio*100)/100,threshold:threshold,fg:hex(fg),bg:hex(bg),tag:el.tagName.toLowerCase(),text:clean(el.innerText||el.textContent).slice(0,100),x:Math.round(r.x),y:Math.round(r.y)});
 }
 const rects=nodes.slice(0,8000).map(e=>e.getBoundingClientRect()).filter(r=>r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth);
 // Approximate viewport occupancy of leaf text and media only; not a full layout quality judgement.
 let grid=new Set();for(const e of nodes.slice(0,8000)){if(!e.matches('img,video,svg,canvas,button,input,textarea,select')&&!Array.from(e.childNodes).some(n=>n.nodeType===3&&clean(n.nodeValue)))continue;let r=e.getBoundingClientRect();let x0=Math.max(0,Math.floor(r.left/innerWidth*40)), x1=Math.min(39,Math.floor(r.right/innerWidth*40)),y0=Math.max(0,Math.floor(r.top/innerHeight*24)),y1=Math.min(23,Math.floor(r.bottom/innerHeight*24));for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)grid.add(y*40+x)}
 return {source_headings:q('h1,h2,h3').map(el=>({level:el.tagName,text:clean(el.innerText||el.textContent).slice(0,200)})).filter(x=>x.text).slice(0,30),content_text:text.slice(0,24000),content_truncated:text.length>24000,words,nodes:nodes.length,total_nodes:all.length,truncated,h1:heads.length,h2:h2.length,images:images.length,alt_missing:images.filter(x=>!x.hasAttribute('alt')).length,controls:controls.length,nameless_controls:controls.filter(x=>!name(x)).length,links:links.length,nameless_links:links.filter(x=>!name(x)).length,fields:fields.length,unlabelled_fields:fields.filter(x=>!labeled(x)).length,fonts:fonts.size,colors:Object.entries(colors).sort((a,b)=>b[1]-a[1]).slice(0,6).map(x=>x[0]),contrasts,whitespace:Math.round((1-grid.size/960)*100),title:!!clean(document.title),language:!!document.documentElement.lang,viewport:!!document.querySelector('meta[name="viewport" i]'),iframes:q('iframe').length,viewport_width:innerWidth,viewport_height:innerHeight,overflow:Math.max(0,Math.round(document.documentElement.scrollWidth-innerWidth))};
}'''


def _chrome_executable():
    explicit=os.environ.get('VIBEAUDIT_CHROMIUM_PATH')
    if explicit: return explicit
    for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',shutil.which('chromium'),shutil.which('google-chrome')]:
        if p and os.path.isfile(p): return p
    return None


def _collect(url, fetch=_public_get):
    from playwright.sync_api import sync_playwright
    deadline=time.monotonic()+MAX_SECONDS-5
    first, final, hdr=fetch(url,deadline,30 * 1024 * 1024)
    if first.startswith(b'%PDF-'):
        # Return bytes to the parent; multi-page OCR must not share the browser's short timeout.
        return [],{'pdf_content_base64':base64.b64encode(first).decode('ascii')},final
    if len(first)>MAX_RESOURCE: raise ValueError('HTML құжаты рұқсат етілген көлемнен үлкен.')
    if 'html' not in hdr.get('Content-Type','').lower() and b'<html' not in first[:3000].lower() and b'<!doctype' not in first[:3000].lower():
        raise ValueError('Сілтеме HTML бетін қайтармады.')
    state={'requests':0,'blocked':0,'failed':0,'bytes':0,'essential_failed':0,'websockets':0,'page_errors':0,'errors':[],'blocked_reasons':{}}; cache={final:(first,final,hdr)}
    with sync_playwright() as p:
        args=['--disable-quic','--disable-background-networking','--disable-features=WebRtcHideLocalIpsWithMdns','--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--disable-extensions','--disable-default-apps','--disable-background-timer-throttling','--proxy-bypass-list=<-loopback>']
        options={'headless':True,'proxy':{'server':'http://127.0.0.1:9'},'args':args}
        exe=_chrome_executable()
        if exe: options['executable_path']=exe
        browser=p.chromium.launch(**options)
        try:
            ctx=browser.new_context(viewport={'width':1365,'height':768},locale='kk-KZ',service_workers='block',accept_downloads=False,permissions=[])
            ctx.set_default_timeout(15000); ctx.set_default_navigation_timeout(22000)
            def wsblock(ws):
                state['blocked']+=1; state['websockets']+=1
                ws.close()
            ctx.route_web_socket('**/*',wsblock)
            def gate(route):
                req=route.request; state['requests']+=1
                try:
                    scheme=urlsplit(req.url).scheme
                    if scheme in ('data','blob'):
                        route.continue_(); return
                    reason=('method' if req.method!='GET' else 'scheme' if scheme not in ('http','https') else 'request_limit' if state['requests']>MAX_REQUESTS else 'size_limit' if state['bytes']>=MAX_BYTES else 'time_limit' if time.monotonic()>deadline else '')
                    if reason:
                        state['blocked_reasons'][reason]=state['blocked_reasons'].get(reason,0)+1
                        state['blocked']+=1
                        if req.resource_type in ('script','stylesheet','document','xhr','fetch'): state['essential_failed']+=1
                        route.abort(); return
                    if req.url in cache: data,_,heads=cache.pop(req.url)
                    else:
                        browser_headers=req.headers
                        permitted={key:value for key,value in browser_headers.items() if key.lower() in ('user-agent','accept','accept-language','referer','origin')}
                        data,actual,heads=(fetch(req.url,deadline,min(MAX_RESOURCE,MAX_BYTES-state['bytes']),request_headers=permitted) if fetch is _public_get else fetch(req.url,deadline,min(MAX_RESOURCE,MAX_BYTES-state['bytes'])))
                        if actual != req.url:
                            # Browser must apply origin/base URL semantics; every new request passes this gate.
                            route.fulfill(status=302, headers={'Location':actual}, body=b'')
                            return
                    state['bytes']+=len(data); status=int(heads.pop('_vibe_status','200')); route.fulfill(status=status,headers=heads,body=data)
                except Exception as exc:
                    state['failed']+=1
                    if req.resource_type in ('script','stylesheet','document','xhr','fetch'): state['essential_failed']+=1
                    if len(state['errors'])<5: state['errors'].append(str(exc)[:140])
                    try: route.abort()
                    except Exception: pass
            ctx.route('**/*',gate)
            ctx.add_init_script("Object.defineProperty(window,'open',{value:()=>null}); window.RTCPeerConnection=undefined; window.webkitRTCPeerConnection=undefined;")
            page=ctx.new_page()
            page.on('pageerror',lambda error: state.__setitem__('page_errors', state['page_errors']+1))
            try:
                page.goto(final,wait_until='domcontentloaded',timeout=22000)
                page.wait_for_timeout(1500)
                result=page.evaluate(JS)
                try: screenshot='data:image/jpeg;base64,'+base64.b64encode(page.screenshot(type='jpeg',quality=55,timeout=5000)).decode('ascii')
                except Exception: screenshot=None
                try:
                    page.set_viewport_size({'width':390,'height':844}); page.wait_for_timeout(500)
                    mobile=page.evaluate('() => ({width: innerWidth, overflow: Math.max(0, Math.round(document.documentElement.scrollWidth-innerWidth))})')
                except Exception: mobile=None
            except Exception: raise ValueError('Бетті толық ашу мүмкін болмады немесе уақыт шегінен асты.')
            result['url']=page.url
            ctx.close()
        finally: browser.close()
    pairs=result['contrasts']; failing=[x for x in pairs if x['ratio']<x['threshold']]; worst=min(pairs,key=lambda x:x['ratio']) if pairs else None
    partial=bool(state['essential_failed'] or state['websockets'] or state['page_errors'] or result['iframes'] or result['truncated'] or result['words']<15)
    contrast_known=bool(pairs)
    e={'kind':'URL','js_heavy':partial,'scripts':0,'words':result['words'],'h1':result['h1'],'h2':result['h2'],'title':result['title'],'language':result['language'],'viewport':result['viewport'],'images':result['images'],'alt_missing':result['alt_missing'],'controls':result['controls'],'nameless_controls':result['nameless_controls'],'links':result['links'],'nameless_links':result['nameless_links'],'fields':result['fields'],'unlabelled_fields':result['unlabelled_fields'],'css_total':0,'css_loaded':0,'contrast':(worst['ratio'] if contrast_known and worst['threshold']==4.5 else None), 'rendered':True,'contrast_samples':len(pairs),'contrast_failures':len(failing),'contrast_examples':failing[:5], 'resource_stats':state}
    features=[worst['ratio'] if contrast_known else 0, result['whitespace'],result['words'],min(30,result['fonts']),min(30,result['controls']),min(100,(result['h1']+result['h2'])/max(1,result['words']/60)*30)]
    known={'contrast_ratio':contrast_known,'whitespace_ratio':bool(result['nodes']),'text_density':bool(result['words']),'font_variety':bool(result['fonts']),'cta_presence':bool(result['controls']),'visual_hierarchy_score':bool(result['h1'] or result['h2'])}
    note=('Браузерде рендерленген бір ғана 1365×768 көрініс тексерілді. Сілтемелерді басу, кіру, барлық интерактивті күйлер және iframe ішіндегі мазмұн тексерілмейді. Контраст — қабаттасуы толық ескерілмеген мәтін үлгілерінің жуық өлшемі; бос кеңістік — viewport торы бойынша бағалау. '
          + ('Кейбір негізгі ресурстар жүктелмеді немесе шекке жетті; нәтиже толық емес. ' if partial else '')
          + f"Сұраулар: {state['requests']}; бұғатталды: {state['blocked']}; қате: {state['failed']}."
          + (' Ресурс санының шегі жетті.' if state['blocked_reasons'].get('request_limit') else '')
          + (' POST және басқа өзгеріс енгізетін сұраулар қауіпсіздік үшін өшірілген.' if state['blocked_reasons'].get('method') else '')
          + (' Кейбір сыртқы сервер ресурсты бермеді: ' + '; '.join(state['errors'][:2]) + '.' if state['errors'] else ''))
    meta={'palette':result['colors'],'background':worst['bg'] if worst else None,'foreground':worst['fg'] if worst else None,'detail':f"{result['nodes']} көрінетін элемент · {result['words']} сөз · {result['h1']} H1 · {result['images']} сурет",'note':note,'known':known,'evidence':e,'rendered':True,'partial':partial,'source_headings':result.get('source_headings',[]),'content_text':result.get('content_text',''),'content_truncated':result.get('content_truncated',False),'render_details':result,'mobile':mobile,'screenshot':screenshot}
    return features,meta,final


def extract_url(url, safe_fetch=None):
    """Run bounded Chromium worker, return (features, meta, final_url)."""
    kwargs={'stdin':subprocess.PIPE,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'text':True,'encoding':'utf-8'}
    if os.name=='nt': kwargs['creationflags']=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else: kwargs['start_new_session']=True
    proc=subprocess.Popen([sys.executable,os.path.abspath(__file__),'--worker'],**kwargs)
    try: out,err=proc.communicate(json.dumps({'url':url}),timeout=MAX_SECONDS+8)
    except subprocess.TimeoutExpired:
        if os.name=='nt': subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        else: os.killpg(proc.pid,signal.SIGKILL)
        proc.communicate(); raise ValueError('Браузерлік талдаудың уақыт шегі аяқталды.')
    try: result=json.loads(out.strip().splitlines()[-1])
    except Exception: raise ValueError('Браузер іске қосылмады. Playwright және Chromium орнатылуын тексеріңіз.')
    if 'error' in result: raise ValueError(result['error'])
    meta=result['meta']
    if 'pdf_content_base64' in meta:
        import audit_engine
        try: data=base64.b64decode(meta['pdf_content_base64'],validate=True)
        except Exception: raise ValueError('PDF сілтемесін оқу мүмкін болмады.')
        if len(data)>30*1024*1024: raise ValueError('PDF 30 МБ шегінен асады.')
        features,meta,pages=audit_engine.extract_pdf(data)
        meta.update(pdf_url=True,pdf_size_mb=round(len(data)/1024/1024,2),pdf_pages=pages)
        return features,meta,result['url']
    return result['features'],meta,result['url']


def from_chrome_capture(url, result):
    """Validate a user-initiated active-tab snapshot; never access cookies or profiles."""
    if not isinstance(result,dict): raise ValueError('Chrome бетінен алынған дерек жарамсыз.')
    u=urlsplit(url)
    try:
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or len(url)>2048: raise ValueError()
        if u.port is not None and not 1<=u.port<=65535: raise ValueError()
    except ValueError: raise ValueError('Тек HTTP/HTTPS сайты талданады.') from None
    def count(k):
        value=result.get(k)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=200000 or not float(value).is_integer(): raise ValueError('Chrome көрсеткіштері жарамсыз.')
        return int(value)
    keys=['words','nodes','h1','h2','images','alt_missing','controls','nameless_controls','links','nameless_links','fields','unlabelled_fields','fonts','iframes']
    r={k:count(k) for k in keys}
    for bad,total in [('alt_missing','images'),('nameless_controls','controls'),('nameless_links','links'),('unlabelled_fields','fields')]:
        if r[bad]>r[total]: raise ValueError('Chrome көрсеткіштері сәйкес емес.')
    whitespace=result.get('whitespace')
    if isinstance(whitespace,bool) or not isinstance(whitespace,(int,float)) or not 0<=whitespace<=100: raise ValueError('Chrome орналасу көрсеткіші жарамсыз.')
    pairs=[]
    if not isinstance(result.get('contrasts'),list): raise ValueError('Chrome контраст дерегі жарамсыз.')
    for item in result['contrasts'][:400]:
        if not isinstance(item,dict): continue
        ratio=item.get('ratio'); threshold=item.get('threshold')
        if isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not 1<=ratio<=21 or threshold not in (3,4.5): continue
        fg=item.get('fg','');bg=item.get('bg','')
        if not isinstance(fg,str) or not isinstance(bg,str) or not re.fullmatch('#[0-9a-fA-F]{6}',fg) or not re.fullmatch('#[0-9a-fA-F]{6}',bg): continue
        pairs.append({'ratio':float(ratio),'threshold':float(threshold),'fg':fg.lower(),'bg':bg.lower(),'tag':str(item.get('tag',''))[:20],'text':str(item.get('text',''))[:100]})
    rawcolors=result.get('colors',[])
    palette=[c.lower() for c in rawcolors[:6] if isinstance(c,str) and re.fullmatch('#[0-9a-fA-F]{6}',c)] if isinstance(rawcolors,list) else []
    bad=[x for x in pairs if x['ratio']<x['threshold']]
    worst=min(pairs,key=lambda x:x['ratio']) if pairs else None
    # The extension cannot know every pending request or inspect other origins/frames.
    partial=True
    e={'kind':'URL','js_heavy':True,'scripts':0,**{k:r[k] for k in ['words','h1','h2','images','alt_missing','controls','nameless_controls','links','nameless_links','fields','unlabelled_fields']},
       'title':bool(result.get('title')),'language':bool(result.get('language')),'viewport':bool(result.get('viewport')),
       'contrast':worst['ratio'] if worst and worst['threshold']==4.5 else None,'rendered':True,'contrast_samples':len(pairs),
       'contrast_failures':len(bad),'contrast_examples':bad[:5],'resource_stats':{}}
    features=[worst['ratio'] if worst else 0,float(whitespace),r['words'],min(30,r['fonts']),min(30,r['controls']),min(100,(r['h1']+r['h2'])/max(1,r['words']/60)*30)]
    known={'contrast_ratio':bool(pairs),'whitespace_ratio':bool(r['nodes']),'text_density':bool(r['words']),
           'font_variety':bool(r['fonts']),'cta_presence':bool(r['controls']),'visual_hierarchy_score':bool(r['h1'] or r['h2'])}
    meta={'palette':palette,'background':worst['bg'] if worst else None,'foreground':worst['fg'] if worst else None,
          'detail':f"Chrome: {r['nodes']} көрінетін элемент · {r['words']} сөз · {r['h1']} H1 · {r['images']} сурет",
          'note':'Chrome-да өзіңіз таңдаған ашық беттегі көрінген элементтер тексерілді. Кіру деректері алынбады. Басқа қойындылар, iframe ішіндегі бөлік және мобильді көрініс тексерілмеді; ұпай шамамен.',
          'known':known,'evidence':e,'rendered':True,'partial':partial,'source_headings':result.get('source_headings',[]),'content_text':str(result.get('content_text',''))[:24000],'content_truncated':bool(result.get('content_truncated',False)),'mobile':None,'screenshot':None,'capture_source':'chrome_active_tab'}
    return features,meta,url


def evaluate(features,meta,kind='URL'):
    import audit_engine
    assessment=audit_engine.evaluate(features,meta,kind)
    if meta.get('rendered'):
        e=meta['evidence']
        render_check=next((x for x in assessment['checks'] if x['key']=='rendering'),None)
        if render_check:
            stats=e.get('resource_stats',{})
            render_check['evidence']=(f"Chrome көрсеткен мәтін: {e.get('words',0)} сөз; желідегі ресурстардың толықтығы тексерілмеді." if meta.get('capture_source')=='chrome_active_tab' else f"Браузер көрсеткен мәтін: {e.get('words',0)} сөз; жүктелмеген/бұғатталған ресурстар: {stats.get('failed',0)+stats.get('blocked',0)}.")
            render_check['recommendation']=('Ашылған қойындыдағы күйді тексеріңіз; басқа қойындылар, iframe және мобильді көрініс тексерілмейді.' if meta.get('capture_source')=='chrome_active_tab' else 'Сайт толық ашылмады: шектеулі ресурстарды, кіру сұрауын және желіге қолжетімділікті тексеріңіз; бағаланбаған бөлікті қолмен қараңыз.' if meta.get('partial') else 'Басқа беттер мен интерактивті күйлерді қосымша тексеріңіз.')
        c=next((x for x in assessment['checks'] if x['key']=='contrast'),None)
        if c:
            samples=e['contrast_samples']; bad=e['contrast_failures']
            c['status']='unknown' if samples==0 else ('fail' if bad else 'pass')
            c['evidence']=f"{samples} мәтін үлгісінің {bad}-ында өлшенген контраст шектен төмен. Бұл бүкіл бетке WCAG сертификаты емес."
            if meta['partial']:
                c['evidence'] += ' Бет толық ашылмаған; нәтиже тек көрінген үлгілерге қатысты.'
            if bad:
                x=e['contrast_examples'][0]; c['evidence']+=f" Мысал: <{x['tag']}> «{x['text'][:60]}» — {x['ratio']}:1 (шек {x['threshold']}:1)."
        if meta.get('partial'):
            # Results apply only to visible elements, not unseen parts of the page.
            checks={x['key']:x for x in assessment['checks']}
            samples={
                'alt':(e.get('images',0), e.get('alt_missing',0)),
                'names':(e.get('controls',0)+e.get('links',0), e.get('nameless_controls',0)+e.get('nameless_links',0)),
                'labels':(e.get('fields',0),e.get('unlabelled_fields',0)),
                'h1':(e.get('h1',0),max(0,e.get('h1',0)-1)),
            }
            for key,(total,bad_count) in samples.items():
                if total:
                    checks[key]['status']='fail' if bad_count else 'pass'
                    checks[key]['evidence']+=' Бет толық ашылмаған; тек көрінген элементтер есептелді.'
        mobile=meta.get('mobile')
        assessment['checks'].append({'key':'responsive_overflow','title':'Мобильді экрандағы көлденең жылжу','weight':10,'status':'unknown' if mobile is None or (meta['partial'] and mobile['overflow']<=1) else ('fail' if mobile['overflow']>1 else 'pass'),'evidence':'390 px экрандағы артық ен: '+(str(mobile['overflow'])+' px' if mobile is not None else 'өлшенбеді')+'. Бір ғана экран тексерілді.', 'recommendation':'Элементтердің енін шектеп, кесте мен суреттерді мобильді экранға бейімдеңіз; интерактивті күйлерді қолмен тексеріңіз.'})
        # Fractional scoring prevents one failed element from zeroing an entire category.
        checks={x['key']:x for x in assessment['checks']}
        ratios={
            'alt':(e.get('alt_missing',0),e.get('images',0)),
            'names':(e.get('nameless_controls',0)+e.get('nameless_links',0),e.get('controls',0)+e.get('links',0)),
            'labels':(e.get('unlabelled_fields',0),e.get('fields',0)),
            'contrast':(e.get('contrast_failures',0),e.get('contrast_samples',0)),
        }
        for key,(bad_count,total) in ratios.items():
            if total and checks[key]['status'] in ('pass','fail'):
                checks[key]['quality']=round(max(0,min(1,1-bad_count/total)),4)
        total_weight=sum(x['weight'] for x in assessment['checks'])
        a=sum(x['weight'] for x in assessment['checks'] if x['status'] in ('pass','fail'))
        passed=sum(x['weight']*x.get('quality',1 if x['status']=='pass' else 0) for x in assessment['checks'] if x['status'] in ('pass','fail'))
        assessment['coverage']=round(100*a/total_weight) if total_weight else 0
        assessment['score']=round(passed/a*100) if a else None
        assessment['issues']=[f"{x['title']}: {x['evidence']} {x['recommendation']}" for x in assessment['checks'] if x['status']=='fail']
        assessment['limitations']=[f"{x['title']}: {x['evidence']} {x['recommendation']}" for x in assessment['checks'] if x['status']=='unknown']
        assessment['assessment_note']=('Шамамен ұпай тек көрінген бөліктегі тексерулер бойынша; қамту '+str(assessment['coverage'])+'%. Толық UX немесе WCAG сәйкестігі емес.' if assessment['score'] is not None else 'Көрінген бөлікте сандық тексеру өлшенбеді; нәтижелер төменде берілген.')
    return assessment


if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='--worker':
    try:
        request=json.loads(sys.stdin.read()); f,m,u=_collect(request['url']); print(json.dumps({'features':f,'meta':m,'url':u},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:400]},ensure_ascii=False))
