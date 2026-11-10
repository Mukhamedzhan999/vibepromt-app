"""Build a detailed Kazakh repair prompt from observed evidence, not invented facts."""
import re
from hybrid_prompt import build_hybrid_prompt
from collections import Counter

STOP={'және','үшін','менен','арқылы','болып','деген','жеке','барлық','туралы','және','бірге','сияқты','немесе','осы','олар','the','and','with','this','from','that','your','have','бұл','болған','болуы','қажет','қалай','болады','үшін','жоба','сайт','pdf'}
def keywords(text):
    words=re.findall(r"[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё]{4,}",text.lower())
    return [w for w,_ in Counter(w for w in words if w not in STOP).most_common(10)]



def design_direction(kind, goal, meta):
    """Heuristic topic matching; palettes are proposals, not observed document colors."""
    rows=meta.get('evidence',{}).get('page_results',[])
    text=(goal+' '+str(meta.get('content_text',''))+' '+' '.join(str(p.get('prompt_text','')) for p in rows)).lower()
    themes=[
        (('психолог','эмоци','mental','therapy','денсаул','health','медицин','тарих','әдебиет'),'жылы әрі сенімді бежевый-қоңыр','жылы бежевый #F2E6D5','қою қоңыр #35251D','қоңыр #70432F','крем #E4D2BA'),
        (('ойын','музыка','sport','спорт','креатив','cinema','кино'),'серпінді қара-қызыл','көмір-қара #121016','ашық крем #F8F1EC','қызыл #E05D59','қою бордо #381B24'),
        (('технолог','программ','software','digital','код','бағдарлам','білім','оқу','мектеп','студент','education','student'),'қою көк әрі заманауи','қою көк #0B132B','ашық көкшіл-ақ #F3F6FF','көк #93B4FF','көк-сұр #1C2B4A')]
    chosen=next((x for x in themes if any(w in text for w in x[0])),None)
    if chosen: _,tone,bg,ink,accent,support=chosen
    else: tone,bg,ink,accent,support=('қара және қою көк','көмір-қара #10131C','ашық сұр-ақ #F2F5FA','көк #A4BAFF','көк-сұр #242B3B')
    base=('ТҮС ПАЛИТРАСЫ — МАЗМҰНҒА ҚАРАЙ ЖУЫҚ ҰСЫНЫС\nНегізгі бағыт: '+tone+'. '
          'Негізгі фон: '+bg+'; негізгі мәтін: '+ink+'; екпін: '+accent+'; карталар не қосымша бет: '+support+'. '
          'Қосымша бағыттар: қою көк #0B132B + ашық мәтін #F3F6FF + көк екпін #93B4FF; '
          'қара #121016 + ашық мәтін #F8F1EC + қызыл екпін #E05D59; '
          'бежевый #F2E6D5 + қою қоңыр мәтін #35251D + қоңыр екпін #70432F. '
          'Тақырыпқа ең үйлесімді бір бағытты таңда, аппақ фонды әдепкі етіп қолданба; '
          'қараңғы фонға ашық мәтін, бежевый фонға қою мәтін қолдан. Екпін түсті үлкен тақырып пен бөлшектерде ұқыпты пайдалан. '
          'Қалыпты мәтін/фон жұбын 4.5:1, ірі мәтінді 3:1 деңгейінде тексер; қызыл немесе басқа екпін түсті шағын мәтінге қолданар алдында жеке өлше. '
          'Бренд нұсқаулығы немесе пайдаланушының нақты талабы болса, соны сақта; түстерді контент пен аудиторияға бейімде.')
    if kind=='PDF':
        return base+('\n\nАЙҚЫН ҚАРІП ЖӘНЕ ҚҰЖАТ САПАСЫ\n'
            'Мәтін барлық бетте анық әрі бірізді болсын: қазақтың Ә, Ғ, Қ, Ң, Ө, Ұ, Ү, Һ, І әріптерін қамтитын Noto Sans немесе Arial таңда; '
            'үлгі ретінде негізгі мәтін 11–12 pt, шағын ескерту кемінде 9–10 pt, аралық 1.3–1.5; құжат пішімі мен аудиториясына қарай нақтылап тексер. '
            'Тақырыптарды 16–28 pt иерархиясымен бөл; фонға сай жоғары контрастты мәтін пайдалан, ұзын жолдарды қысқарт, жиектер мен туралауды сақта. '
            'Тақырып үшін Montserrat SemiBold (600), негізгі мәтін үшін Noto Sans Regular (400), көмекші мәтін үшін Noto Sans Medium (500) жұбын бастапқы нұсқа ретінде қарастыр; ресми немесе ұзақ мәтінді құжатта Lora тақырыптары + Noto Sans мәтінін балама ретінде сына. Әр қаріптің нақты файлында Ә, Ғ, Қ, Ң, Ө, Ұ, Ү, Һ, І таңбалары барын алдын ала тексер. '
            'PDF экспорты кезінде қаріптерді файлға енгіз, мәтінді ізделетін және белгіленетін қалдыр, суреттерді анық жеткілікті ажыратымдылықта экспортта; '
            'қазақ әріптері, оқылу реті, баспа және экран көрінісін әр бетте тексер. OCR қате оқыған жерді түпнұсқадан тексер, дерек ойдан қоспа.')
    return base+('\n\nТИПОГРАФИКА ЖӘНЕ ОҚЫЛЫМ\n'
        'Қазақ әріптерін толық қолдайтын Noto Sans немесе соған ұқсас қаріп қолдан; негізгі мәтінді оқуға жеткілікті өлшемде және айқын контрастпен көрсет. '
        'Тақырып, мәтін және көмекші белгілердің иерархиясын біріздендір; шағын экран мен 200% масштабта оқылымын тексер.')


def build_professional_prompt(kind, goal, assessment, meta, css=''):
    """Build a five-section, evidence-grounded design specification."""
    return build_hybrid_prompt(kind, goal, assessment, meta, css=css)


def build_variants(kind, goal, assessment, meta, css=''):
    common = build_professional_prompt(kind, goal, assessment, meta, css)
    return {
        'chatgpt': common.replace('\n', '\nFor ChatGPT: deliver a concrete implementation plan and verification steps.\n', 1),
        'gemini': common.replace('\n', '\nFor Gemini: reason from the captured content and give a structured design specification.\n', 1),
        'claude': common.replace('\n', '\nFor Claude: distinguish observed evidence from recommendations and implementation.\n', 1),
    }


def build_pdf_prompt(goal, assessment, meta):
    return build_professional_prompt('PDF', goal, assessment, meta)

def build_prompt(kind, goal, assessment, meta):
    return build_professional_prompt(kind, goal, assessment, meta)
