import os, re, io, csv, math, socket, ipaddress, sqlite3, random, time, json, secrets, hmac, threading
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin, urlunsplit

import fitz
import numpy as np
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
import urllib3
import audit_engine
import browser_audit
import prompt_builder

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'ui_audit_dataset.csv')
DB = os.path.join(BASE, 'vibe_audit.db')
FEATURES = ['contrast_ratio', 'whitespace_ratio', 'text_density', 'font_variety', 'cta_presence', 'visual_hierarchy_score']
CLASSES = ['Жоғары деңгейлі UI', 'Контраст және типографика қатесі', 'Шамадан тыс жүктелген / мәтін тым көп', 'Аяқталмаған шикі макет']
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024
# Web deployment requires an access password; local version remains unchanged.
WEB_PASSWORD = os.environ.get('VIBEAUDIT_PASSWORD', '')
if len(WEB_PASSWORD) < 20:
    raise RuntimeError('Set VIBEAUDIT_PASSWORD to a random value of at least 20 characters')

from datetime import timedelta
import hashlib
from flask import Response, session, redirect, url_for
app.secret_key = hashlib.sha256(('vibeaudit-session-v1:' + WEB_PASSWORD).encode('utf-8')).digest()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(days=30))
_login_attempts = []
_login_lock = threading.Lock()

@app.before_request
def protect_web():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin=request.headers.get('Origin', '')
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            return Response('Cross-origin request denied', 403)
    if request.path == '/login' or (request.method == 'GET' and request.path in ('/static/vibepromt-logo.svg', '/static/vibepromt-icon-192.png', '/static/vibepromt-icon-512.png', '/static/manifest.webmanifest')):
        return None
    if request.path.startswith('/api/chrome-'):
        return Response('Local Chrome extension is unavailable on hosted deployments.', 404)
    supplied = request.authorization
    if supplied and supplied.username == 'vibeaudit' and hmac.compare_digest((supplied.password or '').encode('utf-8'), WEB_PASSWORD.encode('utf-8')):
        session.permanent=True
        session['authenticated']=True
    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({'error':'Кіру қажет.'}), 401
        return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    error=''
    if request.method == 'POST':
        now=time.monotonic()
        with _login_lock:
            _login_attempts[:]=[x for x in _login_attempts if now-x < 300]
            limited=len(_login_attempts)>=10
            if not limited:
                _login_attempts.append(now)
        if limited:
            return render_template('login.html', error='Көп әрекет жасалды. Бес минуттан кейін қайталаңыз.'), 429
        password=request.form.get('password','')
        if len(password)<=1024 and hmac.compare_digest(password.encode('utf-8'),WEB_PASSWORD.encode('utf-8')):
            session.clear()
            session.permanent=True
            session['authenticated']=True
            with _login_lock: _login_attempts.clear()
            return redirect(url_for('index'))
        error='Құпиясөз қате. Қайта енгізіңіз.'
    return render_template('login.html',error=error)

@app.after_request
def web_privacy_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

CHROME_PAIR_KEY = secrets.token_urlsafe(32)
CHROME_RESULT = {'id':0, 'data':None}
CHROME_LOCK = threading.Lock()

# Four distributions are synthetic teaching examples, not observations of real products.
def make_dataset():
    if os.path.exists(DATA): return
    rng = np.random.default_rng(42)
    centers = [[10, 50, 120, 3, 4, 70], [2.1, 43, 140, 7, 3, 42], [5.5, 12, 550, 6, 7, 23], [5, 77, 35, 1, 0.4, 15]]
    scales = [3.5, 18, 150, 3, 3, 25]
    rows = []
    for label, center in enumerate(centers):
        for _ in range(100):
            vals = np.array(center) + rng.normal(0, scales)
            vals = np.clip(vals, [1, 0, 0, 1, 0, 0], [21, 100, 2000, 30, 30, 100])
            rows.append([*np.round(vals, 3), label])
    with open(DATA, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f); writer.writerow(FEATURES + ['class']); writer.writerows(rows)

def train_models():
    make_dataset()
    with open(DATA, encoding='utf-8-sig', newline='') as f:
        unique = sorted({tuple(row[k] for k in FEATURES + ['class']) for row in csv.DictReader(f)})
    X = np.array([[float(v) if v.strip() else np.nan for v in row[:6]] for row in unique]); y = np.array([int(row[6]) for row in unique])
    Xtrain, Xtest, ytrain, ytest = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)
    results, models = {}, {}
    for name, estimator in [('Random Forest', RandomForestClassifier(n_estimators=160, random_state=42, class_weight='balanced')), ('Logistic Regression', LogisticRegression(max_iter=2000, random_state=42, class_weight='balanced'))]:
        model = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), estimator); model.fit(Xtrain, ytrain)
        pred = model.predict(Xtest); precision, recall, f1, _ = precision_recall_fscore_support(ytest, pred, average='macro', zero_division=0)
        results[name] = {'accuracy': round(accuracy_score(ytest, pred), 3), 'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3), 'matrix': confusion_matrix(ytest, pred, labels=[0,1,2,3]).tolist()}
        models[name] = model
    return models['Random Forest'], results, len(unique)

MODEL, MODEL_RESULTS, DATA_ROWS = train_models()
PROMPT_EXAMPLES = [
 ('сайт жаса', 'Әлсіз'), ('әдемі қыл', 'Әлсіз'), ('make a website', 'Әлсіз'), ('жобаны түзет', 'Әлсіз'), ('бет керек', 'Әлсіз'), ('design app', 'Әлсіз'),
 ('адаптивті сайт жасап түстерін жақсарт', 'Орташа'), ('қолданушыға ыңғайлы интерфейс жаса', 'Орташа'), ('create responsive dashboard with cards', 'Орташа'), ('бетке навигация және батырмалар қос', 'Орташа'), ('қаріп өлшемі мен аралықты түзет', 'Орташа'), ('improve layout and accessibility', 'Орташа'),
 ('Мақсат: студенттерге арналған dashboard. Аудитория: студент. Талаптар: responsive grid, WCAG AA контраст, нақты CTA. Нәтиже: HTML CSS және тексеру критерийлері.', 'Кәсіби'),
 ('Build accessible dashboard for students. Use responsive grid, WCAG AA, clear CTA, hierarchy and output code with acceptance criteria.', 'Кәсіби'),
 ('Мақсат: веб қосымша. Контекст: мобильді құрылғылар. Шектеу: WCAG AA, responsive layout. Нәтиже: код және тест.', 'Кәсіби'),
 ('Design a responsive landing page with accessibility constraints, spacing tokens, color contrast and acceptance criteria for each screen.', 'Кәсіби'),
 ('Аудитория: пайдаланушылар. Компоненттер: навигация, форма, карточка. Талап: контраст, мобильді бейімделу, нәтиже код.', 'Кәсіби')]
NLP = make_pipeline(TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True), LinearSVC(random_state=42))
NLP.fit([x[0] for x in PROMPT_EXAMPLES], [x[1] for x in PROMPT_EXAMPLES])

def init_db():
    with sqlite3.connect(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL, size_mb REAL, pages INTEGER, score INTEGER NOT NULL, class_id INTEGER NOT NULL, created_at TEXT NOT NULL)')
init_db()

def ratio(a,b):
    def lum(h):
        rgb = [int(h[i:i+2], 16)/255 for i in (1,3,5)]
        return sum(w*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for w,v in zip((.2126,.7152,.0722), rgb))
    x,y=sorted([lum(a), lum(b)]); return round((y+.05)/(x+.05), 2)

def colors_from(text):
    found=[]
    for s in re.findall(r'(?<![\w-])#[0-9a-fA-F]{6}(?![\da-fA-F])|(?<![\w-])#[0-9a-fA-F]{3}(?![\da-fA-F])', text):
        s=s.lower()
        if len(s)==4: s='#'+''.join(c*2 for c in s[1:])
        found.append(s)
    return found

def safe_fetch(url, limit=2_000_000):
    # Resolve once and connect to the validated IP; redirects are validated independently.
    for _ in range(4):
        u=urlsplit(url)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.port not in (None,80,443): raise ValueError('Тек стандартты HTTP/HTTPS сілтемесіне рұқсат етіледі.')
        try: addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme=='https' else 80), type=socket.SOCK_STREAM)))
        except OSError: raise ValueError('Домен табылмады.')
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses): raise ValueError('Жергілікті немесе жеке желі мекенжайына рұқсат жоқ.')
        ip=addresses[0]; port=u.port or (443 if u.scheme=='https' else 80)
        headers={'Host': u.hostname, 'User-Agent':'VibeAuditAI/1.0 (+educational UI analysis)', 'Accept':'text/html,text/css;q=0.9,*/*;q=0.1'}
        pool = (urllib3.HTTPSConnectionPool(ip, port=port, timeout=urllib3.Timeout(connect=3, read=5), retries=False, cert_reqs='CERT_REQUIRED', ca_certs=requests.certs.where(), assert_hostname=u.hostname, server_hostname=u.hostname) if u.scheme=='https' else urllib3.HTTPConnectionPool(ip, port=port, timeout=urllib3.Timeout(connect=3, read=5), retries=False))
        path=(u.path or '/') + ('?'+u.query if u.query else '')
        try:
            response=pool.request('GET', path, headers=headers, redirect=False, preload_content=False)
            if response.status in (301,302,303,307,308):
                loc=response.headers.get('Location'); response.close(); pool.close()
                if not loc: raise ValueError('Қайта бағыттау мекенжайы жоқ.')
                url=urljoin(url,loc); continue
            if response.status >= 400: raise ValueError(f'Сайт HTTP {response.status} қатесін қайтарды.')
            chunks=[]; size=0
            for chunk in response.stream(65536, decode_content=True):
                size += len(chunk)
                if size>limit: raise ValueError('Сайт жауабы рұқсат етілген көлемнен үлкен.')
                chunks.append(chunk)
            ctype=response.headers.get('Content-Type',''); response.close(); pool.close()
            return b''.join(chunks).decode('utf-8', 'replace'), url, ctype
        except ValueError: raise
        except Exception: raise ValueError('Сайтқа қосылу мүмкін болмады немесе күту уақыты аяқталды.')
    raise ValueError('Қайта бағыттау саны тым көп.')

def extract_url(url):
    html, final, ctype = safe_fetch(url)
    if 'html' not in ctype.lower() and '<html' not in html.lower() and '<!doctype' not in html.lower(): raise ValueError('Сілтеме HTML бетін қайтармады.')
    soup=BeautifulSoup(html,'html.parser')
    css=' '.join(s.get_text(' ') for s in soup.find_all('style'))+' '+' '.join(x.get('style','') for x in soup.select('[style]'))
    for link in soup.select('link[rel~=stylesheet][href]')[:3]:
        try:
            sheet, _, _ = safe_fetch(urljoin(final, link['href']), 500_000); css += ' '+sheet
        except ValueError: pass
    cs=colors_from(css); counts=Counter(cs); palette=[x for x,_ in counts.most_common(6)]
    # CSS cascade is not computed; these are declaration-based estimates.
    bg_match=re.search(r'(?:background(?:-color)?)\s*:\s*(#[\da-fA-F]{3,6})\b',css, re.I)
    fg_match=re.search(r'(?<![-\w])color\s*:\s*(#[\da-fA-F]{3,6})\b',css, re.I)
    def norm(m, default):
        c=colors_from(m.group(1)) if m else []; return c[0] if c else default
    bg=norm(bg_match,'#ffffff'); fg=norm(fg_match,'#111827')
    for e in soup(['script','style','noscript','svg']): e.decompose()
    words=len(soup.get_text(' ',strip=True).split()); nodes=soup.find_all(True); headings=len(soup.select('h1,h2')); ctas=len(soup.select('button, a[href], input[type=submit], input[type=button]'))
    families=set(re.findall(r'font-family\s*:\s*([^;}{]+)',css,re.I)); sizes=set(re.findall(r'font-size\s*:\s*([^;}{]+)',css,re.I))
    depth=max((len(list(n.parents)) for n in nodes), default=0)
    whitespace=max(3,min(90, 68-words/25-len(nodes)/75))
    features=[ratio(bg,fg),whitespace,words,len(families)+len(sizes) or 1,min(ctas,30),min(100, headings/max(1,words/60)*30)]
    return features, {'palette':list(dict.fromkeys([bg,fg]+palette))[:6], 'background':bg,'foreground':fg,'detail':f'{len(nodes)} DOM түйіні · {depth} деңгей · {len(soup.select("img"))} сурет · {len(soup.select("img:not([alt]), img[alt="" ]")) if False else sum(1 for img in soup.select("img") if not img.get("alt"))} alt мәтінсіз', 'note':'HTML және CSS декларациялары бойынша бағалау; JavaScript орындалмайды, орналасу мен нақты cascade есептелмейді.'}, final

def extract_pdf(data):
    try: doc=fitz.open(stream=data, filetype='pdf')
    except Exception: raise ValueError('PDF файлын оқу мүмкін болмады.')
    try:
        if doc.needs_pass: raise ValueError('Құпиясөзбен қорғалған PDF қолдау таппайды.')
        n=len(doc)
        if not n: raise ValueError('PDF ішінде бет жоқ.')
        indices=sorted(set(round(i*(n-1)/14) for i in range(15))) if n>15 else list(range(n))
        words=[]; whites=[]; fontset=set(); ctas=[]; hier=[]; colors=[]
        for i in indices:
            p=doc.load_page(i); d=p.get_text('dict'); spans=[]; occupied=0
            for block in d.get('blocks',[]):
                if block.get('type')==1:
                    r=fitz.Rect(block['bbox']) & p.rect; occupied+=max(0,r.get_area()); continue
                for line in block.get('lines',[]):
                    for s in line.get('spans',[]):
                        if not s.get('text','').strip(): continue
                        spans.append(s); fontset.add((s.get('font',''),round(s.get('size',0))))
                        r=fitz.Rect(s['bbox']) & p.rect; occupied+=max(0,r.get_area())
                        colors.append('#%06x' % (s.get('color',0)&0xffffff))
            text=p.get_text('text'); wc=len(text.split()); words.append(wc)
            whites.append(max(0,min(100,100*(1-min(1,occupied/max(1,p.rect.get_area()))))))
            ctas.append(len(p.get_links()))
            sizes=[s.get('size',0) for s in spans]; med=float(np.median(sizes)) if sizes else 0
            large=sum(1 for s in spans if s.get('size',0)>med*1.25 and len(s.get('text',''))<160)
            hier.append(min(100,large/max(1,wc/60)*30))
        fg=Counter(colors).most_common(1)[0][0] if colors else '#111827'; bg='#ffffff'
        return [ratio(bg,fg), float(np.mean(whites)),float(np.mean(words)),min(30,len(fontset)),min(30,float(np.mean(ctas))),float(np.mean(hier))], {'palette':list(dict.fromkeys([bg,fg]+[c for c,_ in Counter(colors).most_common(5)]))[:6], 'background':bg,'foreground':fg,'detail':f'{n} бет · {len(indices)} бет талданды', 'note':'Таңдалған беттердің орташа мәні. Бос кеңістік блок шекарасымен жуықталады; фон ақ деп алынады, сканерленген беттерге OCR қолданылмайды.'}, n
    finally: doc.close()

def finish(features, meta, kind, source, prompt='', size=None, pages=None, persist=True):
    f=[round(float(x),2) for x in features]; cls=int(MODEL.predict([f])[0])
    contrast,white,density,fonts,cta,hier=f
    # Transparent heuristic score; not model confidence.
    score=round(max(0,min(100, 100 - (20 if contrast<4.5 else 0) - (15 if white<25 or white>80 else 0) - (20 if density>350 else 0) - (10 if fonts>8 else 0) - (15 if cta<1 else 0) - (15 if hier<25 else 0))))
    issues=[]
    if contrast<4.5: issues.append('Мәтін контрастын кемінде WCAG AA 4.5:1 деңгейіне жеткіз.')
    if white<25 or white>80: issues.append('Компоненттер аралығын 8 px жүйесімен реттеп, бос кеңістікті теңгер.')
    if density>350: issues.append('Ұзын мәтінді қысқартып, мазмұнды тақырыптары бар блоктарға бөл.')
    if fonts>8: issues.append('Қаріп өлшемдері мен отбасыларын ықшам типографиялық шкалаға біріктір.')
    if cta<1: issues.append('Негізгі әрекетке анық атауы бар, көзге түсетін CTA қос.')
    if hier<25: issues.append('Бір негізгі тақырып пен логикалық H2 құрылымын қолдан.')
    if not issues: issues.append('Қолданыстағы иерархияны сақтап, пернетақта және мобильді құрылғыларда тексер.')
    goal=prompt.strip()[:1500] or 'Қолданушыға түсінікті әрі қолжетімді интерфейс жасау.'
    mega='РӨЛ: Сен тәжірибелі UI/UX дизайнері және frontend инженері бол.\n\nМАҚСАТ: '+goal+'\n\nТАЛДАУҒА СҮЙЕНГЕН МІНДЕТТЕР:\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(issues))+'\n\nIMPLEMENTATION: Semantic HTML, responsive CSS Grid/Flexbox, 8px spacing tokens, visible focus states және keyboard navigation қолдан. Негізгі мәтін үшін contrast ratio ≥ 4.5:1 тексер. 320px–1440px аралығында макетті бейімде.\n\nНӘТИЖЕ: Толық жұмыс істейтін компоненттерді және қысқа acceptance criteria тізімін бер. Дерек жетіспесе, жорамалды көрсет.'
    snippet=':root {\n  --bg: #07090e;\n  --surface: #151b2b;\n  --text: #f8fafc;\n  --muted: #cbd5e1;\n  --accent: #a5b4fc;\n}\nbody { background: var(--bg); color: var(--text); }\n.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1.5rem; }\na, button { min-height: 44px; }\n:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }'
    if density > 350: snippet += '\n.prose { max-width: 65ch; line-height: 1.7; }'
    if white < 25 or white > 80: snippet += '\n.section { padding-block: clamp(2rem, 5vw, 5rem); }'
    if fonts > 8: snippet += '\nbody { font-family: system-ui, sans-serif; }\nh1 { font-size: clamp(2rem, 5vw, 3.5rem); }'
    grade=str(NLP.predict([prompt])[0]) if prompt.strip() else None
    if persist:
        with sqlite3.connect(DB) as db: db.execute('INSERT INTO scans(kind,source,size_mb,pages,score,class_id,created_at) VALUES(?,?,?,?,?,?,?)',(kind,source[:250],size,pages,score,cls,datetime.now(timezone.utc).isoformat()))
    return {'features':dict(zip(FEATURES,f)), 'class_id':cls,'class_name':CLASSES[cls], 'score':score,'issues':issues,'prompt':mega,'prompt_grade':grade,'css':snippet,**meta,'kind':kind,'size_mb':size,'pages':pages}



def real_model_prediction(features, meta, kind):
    # Deliberate opt-in: only locally generated, validated, human-labelled models.
    model_path=os.environ.get('VIBEAUDIT_REAL_MODEL', '').strip()
    if not model_path or kind != 'URL' or meta.get('rendered') or meta.get('evidence',{}).get('js_heavy'):
        return None
    if sum(bool(meta.get('known',{}).get(k)) for k in FEATURES) < 3:
        return None
    try:
        if os.path.getsize(model_path)>10_000_000: return None
        with open(model_path,encoding='utf-8') as f: model=json.load(f)
        from train_real_model import infer_real_model
        probs=infer_real_model(model,dict(zip(FEATURES,features)),meta['known'])
        idx=int(np.argmax(probs))
        if probs[idx] < .65: return None
        return {'class_id':idx,'class_name':CLASSES[idx],'confidence':round(probs[idx]*100),
                'note':'Бұл — белгіленген нақты сайттардан алынған модельдің болжамы; пайыз сенімділік кепілі емес.'}
    except (OSError, ValueError, KeyError, TypeError, ImportError, json.JSONDecodeError):
        app.logger.exception('Нақты сайт моделі жүктелмеді')
        return None

def finish_evidence(features, meta, kind, source, prompt='', size=None, pages=None):
    if kind == 'PDF':
        from hybrid_prompt import synchronize_pdf_palette
        synchronize_pdf_palette(meta)
    assessment = browser_audit.evaluate(features, meta, kind) if kind == 'URL' and meta.get('rendered') else audit_engine.evaluate(features, meta, kind)
    known = meta['known']
    f = [round(float(x), 2) if known.get(k, False) else None for k,x in zip(FEATURES, features)]
    failed = [c for c in assessment['checks'] if c['status'] == 'fail']
    unknown = [c for c in assessment['checks'] if c['status'] == 'unknown']
    goal = prompt.strip()[:1500] or ('Құжаттың мазмұнын сақтап, оқылымын және бет дизайнын жақсарту.' if kind == 'PDF' else 'Қолданушыға түсінікті әрі қолжетімді интерфейс жасау.')
    css = (':root {\n  --bg: #07090e;\n  --surface: #151b2b;\n  --text: #f8fafc;\n  --muted: #cbd5e1;\n  --accent: #a5b4fc;\n}\nbody { background: var(--bg); color: var(--text); }\n'
           '.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1.5rem; }\n'
           ':focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }')
    if any(c['key']=='density' for c in failed): css += '\n.prose { max-width: 65ch; line-height: 1.7; }'
    if any(c['key']=='typography' for c in failed): css += '\nbody { font-family: system-ui, sans-serif; }\nh1 { font-size: clamp(2rem, 5vw, 3.5rem); }'
    variants=prompt_builder.build_variants(kind,goal,assessment,meta,css=css)
    mega=variants['chatgpt']
    score=assessment['score']
    prediction=real_model_prediction(features,meta,kind)
    grade=str(NLP.predict([prompt])[0]) if prompt.strip() else None
    with sqlite3.connect(DB) as db:
        db.execute('INSERT INTO scans(kind,source,size_mb,pages,score,class_id,created_at) VALUES(?,?,?,?,?,?,?)', (kind,source[:250],size,pages,score if score is not None else -1,-1,datetime.now(timezone.utc).isoformat()))
    return {'features':dict(zip(FEATURES,f)), 'class_id':None, 'class_name':'Шамамен баға' if score is not None else 'Көрсеткіш өлшенбеді',
            'score':score,'issues':assessment['issues'],'checks':assessment['checks'],'coverage':assessment['coverage'],
            'assessment_note':assessment['assessment_note'], 'limitations':assessment['limitations'], 'model_prediction':prediction, 'prompt':mega, 'prompts':variants,'prompt_grade':grade,'css':css,**meta,'kind':kind,'size_mb':size,'pages':pages}

@app.get('/sw.js')
def service_worker():
    from flask import send_from_directory
    response=send_from_directory(os.path.join(BASE,'static'),'sw.js')
    response.headers['Cache-Control']='no-cache'
    return response

@app.get('/')
def index(): return render_template('index.html', extension_dir=os.path.join(BASE,'chrome-extension'))
def _local_app_request():
    try: host=urlsplit('http://'+request.host).hostname
    except ValueError: return False
    if host not in ('localhost','127.0.0.1') or request.remote_addr not in ('127.0.0.1','::1'): return False
    site=request.headers.get('Sec-Fetch-Site','')
    if site and site not in ('same-origin','none'): return False
    origin=request.headers.get('Origin')
    return not origin or origin in ('http://'+request.host,'https://'+request.host)

@app.get('/api/chrome-key')
def chrome_key():
    if not _local_app_request(): return jsonify({'error':'Тек жергілікті қосымшада қолжетімді.'}),403
    response=jsonify({'key':CHROME_PAIR_KEY})
    response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/chrome-result')
def chrome_result():
    if not _local_app_request(): return jsonify({'error':'Тек жергілікті қосымшада қолжетімді.'}),403
    with CHROME_LOCK: payload=dict(CHROME_RESULT)
    response=jsonify(payload); response.headers['Cache-Control']='no-store'; return response

@app.after_request
def chrome_cors(response):
    origin=request.headers.get('Origin','')
    if request.path=='/api/chrome-audit' and re.fullmatch(r'chrome-extension://[a-p]{32}',origin):
        response.headers['Access-Control-Allow-Origin']=origin
        response.headers['Access-Control-Allow-Methods']='POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers']='Content-Type, X-VibeAudit-Key'
        response.headers['Vary']='Origin'
    return response

@app.route('/api/chrome-audit',methods=['POST','OPTIONS'])
def chrome_audit():
    if request.method=='OPTIONS': return '',204
    origin=request.headers.get('Origin','')
    host=urlsplit('http://'+request.host).hostname
    if host not in ('127.0.0.1','localhost') or request.remote_addr not in ('127.0.0.1','::1') or not re.fullmatch(r'chrome-extension://[a-p]{32}',origin):
        return jsonify({'error':'Тек Chrome кеңейтімі жергілікті компьютерден жібере алады.'}),403
    supplied=request.headers.get('X-VibeAudit-Key','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',supplied) or not hmac.compare_digest(supplied,CHROME_PAIR_KEY): return jsonify({'error':'Жұптау коды қате немесе сервер қайта қосылған. Жаңа кодты көшіріңіз.'}),403
    try:
        if request.content_length is not None and request.content_length>500_000: raise ValueError('Бет деректерінің көлемі тым үлкен.')
        raw=request.get_data(cache=True)
        if len(raw)>500_000: raise ValueError('Бет деректерінің көлемі тым үлкен.')
        body=request.get_json(silent=True)
        if not isinstance(body,dict): raise ValueError('Chrome дерегі жарамсыз.')
        url=body.get('url',''); prompt=body.get('prompt','')
        if not isinstance(url,str) or not isinstance(prompt,str) or len(prompt)>1500: raise ValueError('Chrome дерегі жарамсыз.')
        u=urlsplit(url)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password: raise ValueError('Тек HTTP/HTTPS беті қолданылады.')
        # Never persist path, query, or fragment from a signed-in page.
        source=urlunsplit((u.scheme,u.netloc,'/','',''))
        features,meta,source=browser_audit.from_chrome_capture(source,body.get('result'))
        result=finish_evidence(features,meta,'URL',source,prompt)
        with CHROME_LOCK:
            CHROME_RESULT['id']+=1; CHROME_RESULT['data']=result
        return jsonify({'ok':True})
    except ValueError as exc: return jsonify({'error':str(exc)}),400
    except Exception:
        app.logger.exception('Chrome capture failed'); return jsonify({'error':'Chrome нәтижесін өңдеу мүмкін болмады.'}),500

@app.get('/api/models')
def models(): return jsonify({'models':MODEL_RESULTS, 'rows':DATA_ROWS,'classes':CLASSES})
@app.get('/api/history')
def history():
    with sqlite3.connect(DB) as db:
        db.row_factory=sqlite3.Row
        return jsonify([dict(x) for x in db.execute('SELECT * FROM scans ORDER BY id DESC LIMIT 20')])
PDF_JOBS = {}
PDF_JOB_LOCK = threading.Lock()

@app.post('/api/pdf-jobs')
def start_pdf_job():
    file=request.files.get('file'); prompt=request.form.get('prompt','')
    if not file or not file.filename.lower().endswith('.pdf'): return jsonify({'error':'PDF файлын таңдаңыз.'}),400
    if len(prompt)>5000: return jsonify({'error':'Сипаттама 5000 таңбадан аспауы керек.'}),400
    data=file.read()
    if not data.startswith(b'%PDF-'): return jsonify({'error':'Жарамды PDF файлын таңдаңыз.'}),400
    job_id=secrets.token_urlsafe(24); filename=os.path.basename(file.filename)
    with PDF_JOB_LOCK:
        now=time.time()
        for key in list(PDF_JOBS):
            if now-PDF_JOBS[key]['updated']>3600: PDF_JOBS.pop(key,None)
        PDF_JOBS[job_id]={'state':'running','done':0,'total':0,'updated':now}
    def worker():
        def progress(done,total):
            with PDF_JOB_LOCK:
                if job_id in PDF_JOBS: PDF_JOBS[job_id].update(done=done,total=total,updated=time.time())
        try:
            features,meta,pages=audit_engine.extract_pdf(data,progress=progress)
            result=finish_evidence(features,meta,'PDF',filename,prompt,round(len(data)/1024/1024,2),pages)
            with PDF_JOB_LOCK:
                if job_id in PDF_JOBS: PDF_JOBS[job_id].update(state='done',result=result,updated=time.time())
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else 'PDF талдау кезінде қате шықты.'
            with PDF_JOB_LOCK:
                if job_id in PDF_JOBS: PDF_JOBS[job_id].update(state='error',error=message,updated=time.time())
    threading.Thread(target=worker,daemon=True).start()
    return jsonify({'job_id':job_id}),202

@app.get('/api/pdf-jobs/<job_id>')
def pdf_job_status(job_id):
    with PDF_JOB_LOCK: job=PDF_JOBS.get(job_id); result=dict(job) if job else None
    if not result: return jsonify({'error':'Талдау табылмады. Қайта бастаңыз.'}),404
    response=jsonify(result); response.headers['Cache-Control']='no-store'; return response


def collect_site_pages(url, max_pages=4):
    """Collect public same-origin HTML summaries, with explicit limits."""
    from collections import deque
    from urllib.parse import urldefrag
    start=urlsplit(url)
    origin=(start.scheme.lower(),start.netloc.lower())
    queue=deque([urlunsplit((start.scheme,start.netloc,start.path or '/', '', ''))])
    seen=set(); pages=[]; errors=0; discovered=0
    while queue and len(seen)<max_pages:
        link=queue.popleft()
        if link in seen: continue
        seen.add(link)
        try:
            html, final, ctype=safe_fetch(link, 600000)
            parsed=urlsplit(final)
            if (parsed.scheme.lower(),parsed.netloc.lower())!=origin or ('html' not in ctype.lower() and '<html' not in html.lower()): continue
            soup=BeautifulSoup(html,'html.parser')
            title=' '.join(soup.title.get_text(' ',strip=True).split())[:160] if soup.title else ''
            headings=[' '.join(h.get_text(' ',strip=True).split())[:120] for h in soup.select('h1,h2,h3')[:12]]
            pages.append({'url':final,'title':title,'headings':headings})
            for node in soup.select('a[href]')[:150]:
                raw=node.get('href','')
                u=urlsplit(urljoin(final,raw))
                if (u.scheme.lower(),u.netloc.lower())!=origin or u.query or not u.path or re.search(r'\.(pdf|zip|jpg|png|svg|webp|mp4)\Z',u.path,re.I): continue
                candidate=urlunsplit((u.scheme,u.netloc,u.path,'',''))
                if candidate not in seen and candidate not in queue:
                    discovered+=1
                    if len(queue)<20: queue.append(candidate)
        except Exception:
            errors+=1
    return pages, bool(queue), errors, discovered

def add_site_map_to_prompts(result, url):
    pages, remaining, errors, discovered=collect_site_pages(url)
    lines=['\n\nСАЙТ БЕТТЕРІ: НАҚТЫ ТАБЫЛҒАН ҚҰРЫЛЫМ']
    for page in pages:
        lines.append('- '+page['url']+' | '+(page['title'] or 'Тақырып көрсетілмеген')+' | '+('; '.join(page['headings']) or 'Бөлім атаулары алынбады'))
    lines.append(f'Қамту: {len(pages)} HTML бет; қосымша табылған сілтемелер: {discovered}; ашылмағаны: {errors}. Бұл шектеулі тексеріс; JS арқылы көрінетін контент пен басқа беттер қамтылмауы мүмкін.')
    lines.append('Әр анықталған бет үшін бөлек құрылым мен навигация жаса, барлық белгілі мәтінді және бренд стилін сақта. Тексерілмеген беттерді, мазмұнды не функцияларды ойдан қоспа; қалған беттер бойынша материалды сұра. Той/шақыру сайтында тұлғаларды, күнді, орынды, RSVP, нәзік стильді және түпнұсқа тілін сақта.')
    text='\n'.join(lines)
    result['prompts']={k:v+text for k,v in result['prompts'].items()}
    result['prompt']=result['prompts']['chatgpt']
    result['site_pages']={'pages':pages,'limited':remaining,'errors':errors}
    return result

@app.post('/api/audit')
def audit():
    try:
        kind=request.form.get('kind'); prompt=request.form.get('prompt','')
        if len(prompt)>5000: raise ValueError('Сипаттама 5000 таңбадан аспауы керек.')
        if kind=='URL':
            url=request.form.get('url','').strip()
            if len(url)>2048: raise ValueError('Сілтеме тым ұзын.')
            try:
                features,meta,final=browser_audit.extract_url(url)
            except ValueError as browser_error:
                # A static fallback is explicitly labelled; it does not execute JS.
                try:
                    features,meta,final=audit_engine.extract_url(url,safe_fetch)
                except Exception:
                    raise browser_error
                meta['fallback']=True
                meta['detail']='HTML режимі · '+meta['detail']
                meta['note']='Браузерде ашу мүмкін болмады: '+str(browser_error)[:200]+'. Тек бастапқы HTML талданды, JavaScript орындалмады. '+meta.get('note','')
            if meta.get('pdf_url'):
                result=finish_evidence(features,meta,'PDF',final,prompt,meta.get('pdf_size_mb'),meta.get('pdf_pages'))
            else:
                result=finish_evidence(features,meta,'URL',final,prompt)
                result=add_site_map_to_prompts(result,final)
        elif kind=='PDF':
            file=request.files.get('file')
            if not file or not file.filename.lower().endswith('.pdf'): raise ValueError('PDF файлын таңдаңыз.')
            data=file.read()
            if not data.startswith(b'%PDF-'): raise ValueError('Жарамды PDF файлын таңдаңыз.')
            features,meta,pages=audit_engine.extract_pdf(data); result=finish_evidence(features,meta,'PDF',os.path.basename(file.filename),prompt,round(len(data)/1024/1024,2),pages)
        else: raise ValueError('Талдау түрін таңдаңыз.')
        return jsonify(result)
    except ValueError as e: return jsonify({'error':str(e)}),400
    except Exception:
        app.logger.exception('Audit failed'); return jsonify({'error':'Талдау кезінде қате шықты. Файлды немесе сілтемені тексеріңіз.'}),500
@app.post('/api/demo/<int:case>')
def demo(case):
    examples={1:([11,50,120,3,4,70],'Жақсы стартап интерфейсі'),2:([2.1,40,150,9,3,40],'Төмен контраст'),3:([5,12,580,6,7,20],'Мәтіні шамадан тыс көп')}
    if case not in examples: return jsonify({'error':'Мысал табылмады.'}),404
    features,name=examples[case]; kind=request.form.get('kind','URL'); kind=kind if kind in ('URL','PDF') else 'URL'
    bg,fg=('#ffffff','#aaaaaa') if case==2 else ('#07090e','#f8fafc')
    features[0]=ratio(bg,fg)
    result=finish(features,{'palette':[bg,fg,'#6366f1','#10b981'],'background':bg,'foreground':fg,'detail':'Оқу мысалы · модельге берілген дайын белгілер','note':'Бұл мысал нақты сайтты немесе PDF файлын сканерлемейді.'},kind,'Демо: '+name,request.form.get('prompt',''),.4 if kind=='PDF' else None,3 if kind=='PDF' else None,False)
    demo_assessment={'score':result['score'],'coverage':0,'checks':[{'status':'fail','title':'Оқу мысалы','evidence':issue,'recommendation':'Нәтижені қолмен тексеріңіз.'} for issue in result['issues']]}
    result['prompts']=prompt_builder.build_variants(kind,request.form.get('prompt','') or ('Құжаттың оқылымын жақсарту.' if kind=='PDF' else 'Интерфейсті жақсарту.'),demo_assessment,{'evidence':{'page_results':[]}},css=result['css'])
    result['prompt']=result['prompts']['chatgpt']
    return jsonify(result)
@app.errorhandler(413)
def too_large(e): return jsonify({'error':'Сұрау көлемі 30 МБ шегінен асады.'}),413

if __name__=='__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT','5000')), debug=False)

