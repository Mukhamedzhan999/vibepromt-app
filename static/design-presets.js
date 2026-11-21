(function (root, factory) {
 const presets = factory();
 if (typeof module === 'object' && module.exports) module.exports = presets;
 else root.VibeDesignPresets = presets;
})(globalThis, function () {
 'use strict';

 const entries = [
  ['editorial_warm', ['#F1E5D6', '#E4D2BE', '#79513A', '#16263D', '#201817'],
   'Noto Serif', 'Noto Sans', null,
   'Warm documentary photography, authentic archival material and museum-grade editorial composition.',
   ['history', 'historical', 'culture', 'literature', 'archive', 'museum', 'archaeology', 'heritage', 'тарих', 'мәдениет', 'әдебиет', 'мұра', 'кесене', 'өркениет', 'хандық', 'архив', 'музей', 'истори', 'культур', 'литератур', 'археолог', 'наследие']],
  ['tech_dark', ['#0B0F19', '#131A2A', '#6366F1', '#10B981', '#F8FAFC'],
   'Plus Jakarta Sans', 'Inter', 'JetBrains Mono',
   'Dark studio lighting, macro hardware and readable code details, with sleek product typography and restrained motion.',
   ['it', 'tech', 'technology', 'startup', 'saas', 'software', 'hardware', 'programming', 'developer', 'algorithm', 'ai', 'machine learning', 'cybersecurity', 'api', 'технолог', 'бағдарлам', 'компьютер', 'стартап', 'жасанды интеллект', 'киберқауіпсіз', 'ақпараттық жүй', 'ақпараттық технология', 'информатик', 'программир', 'искусственный интеллект', 'разработ', 'кибербезопас']],
  ['corporate_clean', ['#F8FAFC', '#FFFFFF', '#1E3A8A', '#0EA5E9', '#0F172A'],
   'Manrope', 'Inter', null,
   'Crisp editorial photography, clean comparison grids and high-trust executive clarity.',
   ['business', 'finance', 'investment', 'budget', 'accounting', 'education', 'curriculum', 'lesson', 'university', 'course', 'қаржы', 'бизнес', 'экономик', 'инвестици', 'білім', 'сабақ', 'оқу бағдарлам', 'университет', 'финанс', 'бухгалтер', 'образован', 'учебн', 'школ']],
  ['clinical_fresh', ['#F0FDF4', '#FFFFFF', '#059669', '#0F766E', '#064E3B'],
   'Manrope', 'Inter', null,
   'Bright natural or clinical lighting, sharp subject-specific macro visuals and a clear hierarchy for scientific data.',
   ['science', 'scientific', 'medicine', 'medical', 'clinical', 'clinic', 'biology', 'ecology', 'environment', 'climate', 'laboratory', 'patient', 'ғылым', 'медицин', 'денсаулық', 'аурухана', 'емхана', 'биологи', 'экологи', 'зертхана', 'табиғат', 'наук', 'клиник', 'лаборатор', 'природ']],
  ['modern_bold', ['#FAF7F2', '#EFE9DF', '#E11D48', '#18181B', '#18181B'],
   'Plus Jakarta Sans', 'Inter', null,
   'High-contrast magazine photography, bold typography, emphatic crops and a clear visual hook.',
   ['creative', 'marketing', 'brand', 'campaign', 'portfolio', 'e commerce', 'ecommerce', 'online store', 'product catalog', 'retail', 'wedding', 'маркетинг', 'бренд', 'жарнама', 'портфолио', 'дүкен', 'тауар каталог', 'той', 'креатив', 'интернет магазин', 'реклам', 'свадьб']]
 ];
 const keys = ['background', 'card', 'primary accent', 'secondary accent', 'text'];
 const presets = Object.freeze(Object.fromEntries(entries.map(([id, colors, heading, body, mono, mood]) => [id, Object.freeze({
  id,
  palette: Object.freeze(Object.fromEntries(keys.map((role, index) => [role, colors[index]]))),
  fonts: Object.freeze({heading, body, mono}),
  mood
 })])));
 const domainPresets = {
  TECH_AI: 'tech_dark', HISTORY_CULTURE: 'editorial_warm',
  FINANCE_BUSINESS: 'corporate_clean', ACADEMIC_GUIDE: 'corporate_clean',
  ECO_SCIENCE: 'clinical_fresh', CREATIVE_MARKETING: 'modern_bold', CREATIVE: 'modern_bold'
 };
 const normalize = value => String(value || '').normalize('NFKC').toLowerCase().match(/[\p{L}\p{N}]+/gu) || [];

 function score(tokens, terms) {
  return terms.reduce((total, term) => {
   const words = normalize(term);
   const matched = tokens.some((token, start) => words.every((word, offset) => {
    const candidate = tokens[start + offset];
    return candidate === word || (word.length >= 5 && candidate?.startsWith(word));
   }));
   return total + (matched ? (words.length > 1 ? 4 : 2) : 0);
  }, 0);
 }

 function select({title = '', topic = '', domain = ''} = {}) {
  const titleWords = normalize(title);
  const topicWords = normalize(topic);
  let bestId = domainPresets[domain] || 'corporate_clean';
  let bestScore = 0;
  for (const entry of entries) {
   const [id, , , , , , terms] = entry;
   const value = 3 * score(titleWords, terms) + score(topicWords, terms) + (id === domainPresets[domain] ? 1 : 0);
   if (value > bestScore) {
    bestScore = value;
    bestId = id;
   }
  }
  return presets[bestId];
 }

 return Object.freeze({presets, select});
});
