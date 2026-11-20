from pdf_editorial import analyze as analyze_pdf_editorial
"""Evidence-first static HTML / PDF checks. No browser layout or OCR is claimed."""
import re
import os
import math
import shutil
from threading import Lock
from collections import Counter
from urllib.parse import urljoin

import fitz
from bs4 import BeautifulSoup


def ratio(a, b):
    def lum(h):
        c = [int(h[i:i+2], 16) / 255 for i in (1, 3, 5)]
        return sum(w * (v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4)
                   for w, v in zip((.2126, .7152, .0722), c))
    a, b = sorted((lum(a), lum(b)))
    return round((b + .05) / (a + .05), 2)


def colors_from(value):
    found = re.findall(r'(?<![\w-])#[\da-fA-F]{6}(?![\da-fA-F])|(?<![\w-])#[\da-fA-F]{3}(?![\da-fA-F])', value)
    return [('#' + ''.join(c*2 for c in s[1:]) if len(s) == 4 else s).lower() for s in found]


def _color(value):
    """Accept an entire plain CSS color value only; no assumptions about var() etc."""
    value = value.strip().lower().replace('!important', '').strip()
    named = {'black':'#000000','white':'#ffffff','red':'#ff0000','blue':'#0000ff',
             'gray':'#808080','grey':'#808080','transparent':None}
    if value in named: return named[value]
    if re.fullmatch(r'#[a-f0-9]{3}|#[a-f0-9]{6}', value): return colors_from(value)[0]
    m = re.fullmatch(r'rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)',value)
    if m and max(map(int,m.groups())) <= 255: return '#%02x%02x%02x' % tuple(map(int,m.groups()))
    return None


def _properties(style):
    result = {}
    for part in style.split(';'):
        if ':' in part:
            k, v = part.split(':',1); result[k.strip().lower()] = v.strip()
    return result


def _accessible_name(node, soup):
    if node.get('aria-label','').strip() or node.get('title','').strip(): return True
    ids = node.get('aria-labelledby','').split()
    if ids and any(soup.find(id=i) and soup.find(id=i).get_text(' ',strip=True) for i in ids): return True
    if node.get_text(' ',strip=True): return True
    svg = node.find('svg')
    if svg and (svg.get('aria-label','').strip() or svg.find('title')): return True
    if node.name == 'input' and node.get('value','').strip(): return True
    image = node.find('img', alt=True)
    return bool(image and image.get('alt','').strip())


def extract_url(url, safe_fetch):
    html, final, ctype = safe_fetch(url)
    if 'html' not in ctype.lower() and '<html' not in html.lower() and '<!doctype' not in html.lower():
        raise ValueError('Сілтеме HTML бетін қайтармады.')
    soup = BeautifulSoup(html, 'html.parser')
    script_text = sum(len(s.string or s.get_text()) for s in soup.find_all('script'))
    scripts = len(soup.find_all('script'))
    css = ' '.join(s.get_text(' ') for s in soup.find_all('style'))
    links = soup.select('link[rel~=stylesheet][href]')
    loaded = 0
    for link in links[:3]:
        try:
            sheet, _, _ = safe_fetch(urljoin(final, link['href']), 500_000)
            css += '\n' + sheet; loaded += 1
        except ValueError: pass
    body = soup.body or soup
    # Only an explicit simple body selector/inline pair is eligible for an estimate.
    # It is not a computed style and may be superseded in a browser.
    props = {}
    for selector, declarations in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/','',css,flags=re.S)):
        if any(x.strip() == 'body' for x in selector.split(',')):
            props.update(_properties(declarations))
    if soup.body: props.update(_properties(soup.body.get('style','')))
    bg = _color(props.get('background-color',props.get('background','')))
    fg = _color(props.get('color',''))
    css_uncertain = ('background-image' in props or 'opacity' in props or len(links) > loaded)
    contrast_known = bool(bg and fg and not css_uncertain)
    contrast = ratio(bg,fg) if contrast_known else 0
    palette = list(dict.fromkeys(([bg,fg] if bg and fg else []) + colors_from(css)))[:6]
    title = bool(soup.title and soup.title.get_text(' ',strip=True))
    language = bool(soup.html and soup.html.get('lang','').strip())
    viewport = bool(soup.find('meta',attrs={'name':re.compile('^viewport$',re.I)}))
    for node in soup(['script','style','noscript','template']): node.decompose()
    source_headings=[{'level':h.name.upper(),'text':h.get_text(' ',strip=True)[:200]} for h in body.find_all(['h1','h2','h3']) if h.get_text(' ',strip=True)][:30]
    content_text=body.get_text(' ',strip=True)
    words = len(content_text.split())
    nodes = len(body.find_all(True)); h1 = len(body.find_all('h1')); h2 = len(body.find_all('h2'))
    images = body.find_all('img'); alt_missing = sum(1 for image in images if not image.has_attr('alt'))
    controls = body.select('button, input[type=submit], input[type=button]')
    nameless = sum(1 for c in controls if not _accessible_name(c,soup))
    links_count = len(body.select('a[href]'))
    links_nameless = sum(1 for a in body.select('a[href]') if not _accessible_name(a,soup))
    fields = body.select('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')
    def labelled(x):
        if x.get('aria-label') or x.get('aria-labelledby') or x.find_parent('label'): return True
        return bool(x.get('id') and soup.find('label', attrs={'for':x.get('id')}))
    unlabelled = sum(1 for field in fields if not labelled(field))
    custom = sum(1 for tag in body.find_all(True) if '-' in tag.name)
    js_heavy = script_text > 100_000 or custom > 30 or (words < 80 and scripts >= 3) or any(s in html for s in ('ytInitialData','__NEXT_DATA__','ng-version='))
    families=set(re.findall(r'font-family\s*:\s*([^;}{]+)',css,re.I)); sizes=set(re.findall(r'font-size\s*:\s*([^;}{]+)',css,re.I))
    # Whitespace is unobservable without browser layout; zero means unavailable, not 0%.
    features=[contrast,0,words,min(30,len(families)+len(sizes)),min(30,len(controls)),min(100,(h1+h2)/max(1,words/60)*30)]
    meta={'palette':palette,'background':bg,'foreground':fg,'source_headings':source_headings,'content_text':content_text[:24000],'content_truncated':len(content_text)>24000,
          'detail':f'{nodes} HTML түйіні · {words} сөз · {h1} H1 · {len(images)} сурет',
          'note':'Тек бастапқы HTML талданды. JavaScript, экрандағы нақты орналасу, CSS cascade және интерактивті күйлер тексерілмейді.',
          'known':{'contrast_ratio':contrast_known,'whitespace_ratio':False,'text_density':not js_heavy,'font_variety':bool(css) and not js_heavy,'cta_presence':not js_heavy,'visual_hierarchy_score':not js_heavy},
          'evidence':{'kind':'URL','js_heavy':js_heavy,'scripts':scripts,'script_chars':script_text,'words':words,'h1':h1,'h2':h2,'title':title,'language':language,'viewport':viewport,'images':len(images),'alt_missing':alt_missing,'controls':len(controls),'nameless_controls':nameless,'links':links_count,'nameless_links':links_nameless,'fields':len(fields),'unlabelled_fields':unlabelled,'css_total':len(links),'css_loaded':loaded,'contrast':contrast if contrast_known else None}}
    return features,meta,final


def _sample_pdf_page(page, spans, max_pixels=400000):
    """Return bounded raster observations; not equivalent to a WCAG audit."""
    rect = page.rect
    if rect.width <= 0 or rect.height <= 0:
        return None
    # <=400k pixels and <=1600px on either axis, regardless of paper size.
    scale = min(1.0, math.sqrt(max_pixels/(rect.width*rect.height)), 1600/rect.width, 1600/rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False, annots=True)
    if pix.n != 3 or pix.width * pix.height > 450000:
        return None
    sample_bytes = pix.samples_mv
    def pixel(x,y):
        xx=int((x-rect.x0)*scale); yy=int((y-rect.y0)*scale)
        if not (0 <= xx < pix.width and 0 <= yy < pix.height): return None
        o=yy*pix.stride+xx*pix.n
        return tuple(int(v) for v in sample_bytes[o:o+3])
    # Regular grid is a color sample, not a measurement of usable whitespace.
    counts=Counter()
    for iy in range(25):
        for ix in range(25):
            c=pixel(rect.x0+(ix+.5)*rect.width/25, rect.y0+(iy+.5)*rect.height/25)
            if c:
                counts[tuple(min(255,round(x/16)*16) for x in c)] += 1
    pairs=[]
    # Rotation changes coordinates of text and pixmap; skip these samples to avoid false claims.
    if page.rotation == 0:
        for span in spans[:150]:
            if not span.get('text','').strip(): continue
            b=fitz.Rect(span.get('bbox',()))
            if b.is_empty or b.width < 4 or b.height < 4: continue
            # Points just outside text; reject visually mixed/gradient backgrounds.
            pad=max(1.5,1.5/max(scale,0.01))
            pts=[(b.x0+b.width*t,b.y0-pad) for t in (.2,.5,.8)] + [(b.x0+b.width*t,b.y1+pad) for t in (.2,.5,.8)]
            samples=[v for v in (pixel(x,y) for x,y in pts) if v is not None]
            if len(samples)<4 or any(max(v[j] for v in samples)-min(v[j] for v in samples)>18 for j in range(3)): continue
            bg=tuple(round(sum(v[j] for v in samples)/len(samples)) for j in range(3))
            fg_int=int(span.get('color',0)) & 0xffffff
            fg='#%06x' % fg_int; background='#%02x%02x%02x' % bg
            # Large text is provisionally measured against 3:1, other text 4.5:1.
            size=float(span.get('size',0)); bold=bool(int(span.get('flags',0)) & 16)
            threshold=3.0 if size>=18 or (bold and size>=14) else 4.5
            pairs.append({'ratio':ratio(fg,background),'threshold':threshold,'foreground':fg,'background':background,
                          'size':round(size,1),'snippet':span.get('text','').strip()[:60]})
    return {'colors':counts,'pairs':pairs,'width':pix.width,'height':pix.height}


_PDF_LOCK = Lock()


def extract_pdf(data, progress=None):
    # PyMuPDF objects must not be used by concurrent threads.
    with _PDF_LOCK:
        return _extract_pdf(data, progress)


def _extract_pdf(data, progress):
    """Read every page sequentially; keep only aggregate and per-page diagnostics."""
    try: doc=fitz.open(stream=data,filetype='pdf')
    except Exception: raise ValueError('PDF файлын оқу мүмкін болмады.')
    try:
        if doc.needs_pass: raise ValueError('Құпиясөзбен қорғалған PDF қолдау таппайды.')
        n=len(doc)
        if not n: raise ValueError('PDF ішінде бет жоқ.')
        large_document = n >= 30
        per_page=[]; fonts=set(); links=0; no_text=0; heads=0; graphic=0
        raster_limit=min(n,12)
        raster_pages={round(i*(n-1)/max(1,raster_limit-1)) for i in range(raster_limit)}
        per_page_budget=max(40,min(1200,24000//n)); source_text_truncated=False
        raster_colors=Counter(); worst=[]; contrast_samples=0; low_count=0
        rendered=0; render_errors=0; page_errors=[]; ocr_needed=[]; ocr_failed=[]; ocr_pages=0
        ocr_lang=os.environ.get('VIBEAUDIT_OCR_LANG','kaz+rus+eng').strip() or 'kaz+rus+eng'
        if not re.fullmatch(r'[a-zA-Z0-9_+]{1,40}',ocr_lang): ocr_lang='kaz+rus+eng'
        exe=shutil.which('tesseract')
        if not exe:
            base=os.environ.get('VIBEAUDIT_TESSERACT_DIR','')
            candidate=os.path.join(base,'tesseract.exe') if base else ''
            if candidate and os.path.isfile(candidate): exe=candidate
        tessdata=os.environ.get('TESSDATA_PREFIX','').strip()
        if not tessdata:
            candidate=os.path.join(os.path.dirname(os.path.abspath(__file__)),'tessdata')
            if os.path.isdir(candidate): tessdata=candidate
        if not tessdata and exe:
            candidate=os.path.join(os.path.dirname(exe),'tessdata')
            if os.path.isdir(candidate): tessdata=candidate
        if tessdata:
            available=[x for x in ocr_lang.split('+') if os.path.isfile(os.path.join(tessdata,x+'.traineddata'))]
            ocr_lang='+'.join(available)
        ocr_available=bool(ocr_lang and tessdata and os.path.isdir(tessdata))
        ocr_error=False
        if progress: progress(0,n)
        for i in range(n):
            page_no=i+1; info={'page':page_no,'words':None,'low_contrast':0,'contrast_samples':0,'text_status':'Белгісіз',
                               'small_font_spans':None,'small_font_status':'unavailable','contrast_sum':0.0,'contrast_below_7':None}
            try:
                page=doc.load_page(i)
                blocks=page.get_text('dict',flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES).get('blocks',[])
                spans=[sp for block in blocks for line in block.get('lines',[]) for sp in line.get('spans',[]) if sp.get('text','').strip()]
                native_words=sum(len(sp.get('text','').split()) for sp in spans)
                images=page.get_image_info(); graphic+=len(images); info['image_count']=len(images)
                image_text_possible=bool(images) and (
                    native_words < 12 or any(
                        (fitz.Rect(image['bbox']) & page.rect).get_area() >= page.rect.get_area() * .65
                        for image in images
                    ) and (not large_document or native_words < 45)
                )
                if images and not image_text_possible:
                    info['image_text_not_checked']=True
                used_ocr=False
                if image_text_possible:
                    ocr_needed.append(page_no)
                    if ocr_available:
                        try:
                            dpi = 120 if large_document else 150
                            textpage=page.get_textpage_ocr(language=ocr_lang,dpi=dpi,full=(native_words<5),tessdata=tessdata or None)
                            ocr_blocks=page.get_text('dict',textpage=textpage,flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES).get('blocks',[])
                            recognized=[sp for block in ocr_blocks for line in block.get('lines',[]) for sp in line.get('spans',[]) if sp.get('text','').strip()]
                            if recognized:
                                spans=recognized; blocks=ocr_blocks; used_ocr=True; ocr_pages+=1
                                info['text_status']='OCR арқылы оқылды; қолмен тексеру қажет'
                            else:
                                ocr_failed.append(page_no); info['text_status']='OCR мәтін таппады'
                        except Exception:
                            ocr_error=True; ocr_failed.append(page_no); info['text_status']='OCR орындалмады'
                    else:
                        ocr_failed.append(page_no); info['text_status']='Суреттегі мәтін OCR-сыз тексерілмеді'
                elif not native_words:
                    info['text_status']='Мәтін жоқ немесе бет бос'
                else:
                    info['text_status']='PDF мәтіні оқылды'
                if not used_ocr:
                    for sp in spans: fonts.add((sp.get('font',''),round(sp.get('size',0),1)))
                    info['small_font_spans']=sum(1 for sp in spans if 0<float(sp.get('size',0))<10.5)
                    info['small_font_status']='native_only' if image_text_possible else 'native'
                else:
                    info['small_font_status']='ocr_unavailable'
                wc=sum(len(sp.get('text','').split()) for sp in spans); info['words']=wc
                lines=[]
                for block in blocks:
                    for line in block.get('lines',[]):
                        line_spans=[sp for sp in line.get('spans',[]) if sp.get('text','').strip()]
                        text=''.join(sp['text'] for sp in line_spans).strip()
                        if text:
                            size=max((float(sp.get('size',0)) for sp in line_spans),default=0)
                            lines.append((text,size))
                page_text='\n'.join(text for text,_ in lines)
                info['_analysis_text']=page_text[:20000]
                info['_analysis_truncated']=len(page_text)>20000
                # OCR-generated font sizes do not reliably represent source typography.
                info['_page_heading']=(max(lines,key=lambda item:item[1])[0] if lines and not used_ocr
                                       else (lines[0][0] if lines else None))
                sizes=[float(sp.get('size',0)) for sp in spans if sp.get('size',0)>0]
                body_size=sorted(sizes)[len(sizes)//2] if sizes else 0
                candidates=[(text,size) for text,size in lines if 4<=len(text)<=130 and len(text.split())<=18 and not re.fullmatch(r'[\d\W_]+',text)]
                larger=[text for text,size in candidates if body_size and size>=body_size*1.15]
                info['_heading_candidates']=larger[:6] if larger else ([text for text,_ in candidates[:1]] if used_ocr else [])
                info['text_excerpt']=page_text[:180]
                info['prompt_text']=page_text[:per_page_budget]
                if len(page_text)>per_page_budget: source_text_truncated=True
                if wc<5: no_text+=1
                links+=len(page.get_links())
                if spans and not used_ocr:
                    sizes=sorted(sp.get('size',0) for sp in spans); median=sizes[len(sizes)//2]
                    heads+=sum(1 for sp in spans if sp.get('size',0)>median*1.25 and len(sp.get('text',''))<160)
                try:
                    observed=_sample_pdf_page(page, [] if used_ocr else spans, 240000 if large_document else 400000) if i in raster_pages else None
                    if observed:
                        rendered+=1; raster_colors.update(observed['colors'])
                        page_pairs=observed['pairs']; page_low=[x for x in page_pairs if x['ratio']<x['threshold']]
                        info['contrast_samples']=len(page_pairs); info['low_contrast']=len(page_low)
                        info['contrast_sum']=sum(pair['ratio'] for pair in page_pairs)
                        info['contrast_below_7']=sum(pair['ratio']<7 for pair in page_pairs) if page_pairs else None
                        contrast_samples+=len(page_pairs); low_count+=len(page_low)
                        worst=sorted(worst+[{**pair,'page':page_no} for pair in page_pairs],key=lambda x:x['ratio'])[:3]
                    elif i in raster_pages: render_errors+=1
                except Exception: render_errors+=1
            except Exception:
                page_errors.append(page_no); info['text_status']='Бетті оқу кезінде қате шықты'
            per_page.append(info)
            if progress: progress(i+1,n)
        valid_words=[p['words'] for p in per_page if p['words'] is not None]
        avg=sum(valid_words)/len(valid_words) if valid_words else 0
        hierarchy=min(100,heads/max(1,sum(valid_words)/60)*30)
        needs_ocr=bool(ocr_failed or page_errors)
        has_contrast=contrast_samples>=3
        contrast=worst[0]['ratio'] if has_contrast else 0
        palette=['#%02x%02x%02x' % c for c,_ in raster_colors.most_common(6)]
        font_known=bool(fonts) and not page_errors and not ocr_failed and ocr_pages==0
        text_known=not needs_ocr and bool(valid_words)
        features=[contrast,0,round(avg,2),min(30,len(fonts)),round(links/max(1,n),2),round(hierarchy,2)]
        note=(f'Барлық бет мәтінге тексерілді. Контраст {rendered} үлгі беттегі мәтін мен фоннан шамамен өлшенді. '
              'OCR сканерленген немесе мәтіні аз суретті беттерде қолданылады. Басқа суреттердегі мәтін, градиент және толық қолжетімділік қолмен тексеріледі.')
        if ocr_failed: note+=f' OCR қолданылмаған немесе сәтсіз беттер: {len(ocr_failed)}; бет тізімі төменде көрсетілген.'
        if page_errors: note+=f' Оқу қатесі шыққан беттер: {len(page_errors)}.'
        if render_errors: note+=f' Растрланбаған беттер: {render_errors}.'
        if ocr_pages: note+=f' OCR {ocr_pages} бетке қолданылды ({ocr_lang}); танылған мәтінді қолмен тексеріңіз.'
        editorial=analyze_pdf_editorial(per_page)
        meta={'palette':palette,'background':None,'foreground':None,
              'detail':f'{n} бет · {n-len(page_errors)} бет оқылды · {rendered} бет растрланды · орташа {avg:.0f} сөз/бет',
              'note':note,
              'known':{'contrast_ratio':has_contrast,'whitespace_ratio':False,'text_density':text_known,'font_variety':font_known,'cta_presence':False,'visual_hierarchy_score':False},
              'evidence':{'kind':'PDF','sampled':n,'pages':n,'sampled_pages':list(range(1,n+1)),
                'editorial':editorial,'words_avg':round(avg,1),'words_max':max(valid_words,default=0),'words_min':min(valid_words,default=0),
                'pages_without_text':no_text,'needs_ocr':needs_ocr,'page_errors':page_errors,'page_results':per_page,
                'source_text_truncated':source_text_truncated,'ocr_needed_pages':ocr_needed,'ocr_failed_pages':ocr_failed,'font_variants':len(fonts),'heading_candidates':heads,
                'links':links,'images':graphic,'rendered_pages':rendered,'raster_sample_pages':sorted(i+1 for i in raster_pages),'render_errors':render_errors,'contrast_samples':contrast_samples,
                'low_contrast_count':low_count,'contrast_examples':worst,'ocr_available':ocr_available,'ocr_pages':ocr_pages,'ocr_error':ocr_error,'ocr_language':ocr_lang,'truncated':False}}
        return features,meta,n
    finally: doc.close()

def evaluate(features, meta, kind):
    """Weighted checks with evidence and availability; not a prediction of overall UX."""
    e=meta.get('evidence',{}); checks=[]
    def check(key, title, weight, status, evidence, recommendation):
        checks.append({'key':key,'title':title,'weight':weight,'status':status,'evidence':evidence,'recommendation':recommendation})
    if kind=='URL':
        js=e.get('js_heavy',False)
        check('rendering','Көрінетін бетті қамту',0,'unknown' if js else 'pass',f"{e.get('scripts',0)} скрипт · HTML мәтіні {e.get('words',0)} сөз",'JavaScript арқылы салынған интерфейсті браузерде рендерлеп, қайта тексеріңіз.' if js else 'Динамикалық күйлерді браузерде қосымша тексеріңіз.')
        check('contrast','Мәтін контрасты',20,'unknown' if e.get('contrast') is None else ('pass' if e['contrast']>=4.5 else 'fail'),f"Body CSS жұбы: {e['contrast']}:1" if e.get('contrast') is not None else 'Сенімді фон және мәтін жұбы анықталмады.','Нақты элементтердің есептелген мәтін/фон түстерін тексеріп, қалыпты мәтінге кемінде 4.5:1 контраст беріңіз.')
        check('h1','Негізгі тақырып',15,'unknown' if js else ('pass' if e.get('h1')==1 else 'fail'),f"H1 саны: {e.get('h1',0)}",'Әр бетке оның мазмұнын сипаттайтын бір H1 қойыңыз; бөлімдерді H2 арқылы реттеңіз.')
        images=e.get('images',0); missing=e.get('alt_missing',0)
        check('alt','Сурет сипаттамалары',15,'unknown' if js or not images else ('pass' if not missing else 'fail'),f"{images} суреттің {missing}-інде alt атрибуты жоқ",'Мағыналы суреттерге қысқа alt сипаттамасын беріңіз; сәндік суретке alt="" қолданыңыз.')
        controls=e.get('controls',0); nameless=e.get('nameless_controls',0); links=e.get('links',0); lbad=e.get('nameless_links',0)
        check('names','Басқару элементінің атауы',15,'unknown' if js or controls+links==0 else ('pass' if nameless+lbad==0 else 'fail'),f"Атаусыз батырма: {nameless}/{controls}; атаусыз сілтеме: {lbad}/{links}",'Батырма мен сілтемеге көрінетін нақты мәтін немесе aria-label беріңіз.')
        fields=e.get('fields',0); unlabelled=e.get('unlabelled_fields',0)
        check('labels','Форма белгілері',10,'unknown' if js or not fields else ('pass' if not unlabelled else 'fail'),f"Белгісіз өріс: {unlabelled}/{fields}",'Әр өріске байланысты label немесе қолжетімді атау қосыңыз.')
        check('viewport','Мобильді viewport',10,'pass' if e.get('viewport') else 'fail','Viewport meta тегі '+('бар' if e.get('viewport') else 'табылмады'),'width=device-width, initial-scale=1 viewport тегін қосыңыз және әр экран өлшемін браузерде тексеріңіз.')
        check('language','Бет тілі',10,'pass' if e.get('language') else 'fail','HTML lang атрибуты '+('бар' if e.get('language') else 'табылмады'),'html элементіне құжаттың тілін көрсететін lang атрибутын қосыңыз.')
        check('title','Бет атауы',5,'pass' if e.get('title') else 'fail','Title тегі '+('бар' if e.get('title') else 'табылмады'),'Әр бетке мазмұнын сипаттайтын бірегей title қосыңыз.')
        if js: 
            for c in checks:
                if c['key'] in ('contrast','viewport','language','title'): c['status']='unknown'
    else:
        ocr=e.get('needs_ocr',False); avg=e.get('words_avg',0); mx=e.get('words_max',0)
        sampled=e.get('sampled',0); pages=e.get('pages',0)
        check('coverage','Беттерді қамту',0,'pass' if sampled==pages and not e.get('render_errors') and not e.get('page_errors') else 'unknown',
              f"{pages} беттің {sampled}-і талданды, {e.get('rendered_pages',0)}-і растрланды.",
              'Өңделмеген немесе растрланбаған беттерді қайта тексеріңіз; уақыт PDF күрделілігіне байланысты.')
        check('ocr','Мәтінді оқу мүмкіндігі',0,'unknown' if ocr else 'pass',
              f"OCR қажет немесе сәтсіз беттер: {', '.join(map(str,e.get('ocr_failed_pages',[])[:30])) or 'жоқ'}; OCR қолданылған бет: {e.get('ocr_pages',0)}.",
              'Суреттегі мәтінді OCR арқылы қайта тексеріңіз; танылған мәтінді түпнұсқамен салыстырыңыз.')
        check('density','Мәтін тығыздығы',35,('fail' if avg>350 or mx>600 else 'pass') if any((p.get('words') or 0)>0 for p in e.get('page_results',[])) else 'unknown',
              f"Орташа {avg} сөз/бет; ең көбі {mx} сөз/бет (бет: {', '.join(str(p['page']) for p in e.get('page_results',[]) if p['words']==mx) or 'белгісіз'}).",
              'Ұзын мәтінді қысқартып, абзац пен бөлімдерге бөліңіз. Шекті құжат мақсатына қарай қолмен бағалаңыз.')
        fonts=e.get('font_variants',0)
        check('typography','Типографика жүйесі',25,'unknown' if not meta.get('known',{}).get('font_variety') else ('fail' if fonts>12 else 'pass'),
              f"Барлық оқылған беттерде {fonts} қаріп пен өлшем комбинациясы.",
              'Қаріп өлшемдерін тақырып, мәтін және ескертпеге арналған шектеулі шкалаға келтіріңіз.')
        examples=e.get('contrast_examples',[]); samples=e.get('contrast_samples',0); low=e.get('low_contrast_count',0)
        contrast_evidence=(f"{samples} мәтін үзіндісінің {low}-інде төмен контраст байқалды; " +
                           ('ең төмені ' + str(examples[0]['ratio']) + ':1, ' + str(examples[0]['page']) + '-бет.' if examples else '')) if samples>=3 else f"Тек {samples} сенімді жергілікті фон үлгісі бар; контраст бағаланбайды."
        check('contrast','Мәтін контрасты (жуық)',20,'unknown' if samples<3 else ('fail' if low else 'pass'),contrast_evidence,
              'Көрсетілген беттердегі мәтін/фон жұбын тексеріңіз: қалыпты мәтін ≥4.5:1, үлкен мәтін ≥3:1. Жергілікті растр үлгісі WCAG сәйкестігін растамайды.')
        check('layout','Бос кеңістік және иерархия',20,'unknown',
              f"Ірі қаріппен жазылған {e.get('heading_candidates',0)} үзінді анықталды; бұл нақты құрылымдық тақырып емес.",
              'Әр беттегі тақырыптарды, топтастыру мен бос аралықтарды визуалды тексеріңіз.')
    available=sum(x['weight'] for x in checks if x['status'] in ('pass','fail'))
    passed=sum(x['weight'] for x in checks if x['status']=='pass')
    # Normalise only observed checks. Unknown checks never silently become a pass.
    score=round(passed/available*100) if available else None
    failed=[x for x in checks if x['status']=='fail']
    unknown=[x for x in checks if x['status']=='unknown']
    return {'score':score, 'coverage':available, 'checks':checks,
            'issues':[f"{c['title']}: {c['evidence']}. {c['recommendation']}" for c in failed],
            'limitations':[f"{c['title']}: {c['evidence']} {c['recommendation']}" for c in unknown],
            'score_label':'Шамамен алынған ұпай',
            'assessment_note':('Шамамен бағалау тек өлшенген тармақтар бойынша жасалды; белгісіз тармақтар есепке кірмейді. Қамту '+str(available)+'%. Толық UI/UX немесе WCAG сараптамасы емес.' if score is not None else 'Өлшенген тармақтар жоқ; қолжетімді деректер төменде көрсетілген.')}
