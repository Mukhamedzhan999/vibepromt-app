(function (root, factory) {
 if (typeof module === 'object' && module.exports) module.exports = factory(require('./design-presets.js'));
 else root.VibeProductionPrompts = factory(root.VibeDesignPresets);
})(globalThis, function (designPresets) {
 'use strict';

 const LANGUAGES = {kk: 'Kazakh', ru: 'Russian', en: 'English'};
 const EVIDENCE_LIMITS = {short: 180, medium: 330, full: 600};
 const subjectFlows = {
  editorial_warm: 'Place people, events and works in their documented time and place. Use a dated timeline or a comparison of genuine sources where it clarifies the subject.',
  tech_dark: 'Explain the actual problem, how the system works and one concrete use case. Pair a component breakdown with a practical workflow or a measured trade-off when supported.',
  corporate_clean: 'Define the decision or learning objective. Compare meaningful alternatives against the same criteria and state the next action, student exercise or decision supported by the evidence.',
  clinical_fresh: 'Show the method, observations, units, sample or study context, findings and limitations. Keep correlation, causation and unverified hypotheses distinct.',
  modern_bold: 'Define the audience and offer. Use specific product attributes, a substantiated example and an actionable next step. Use exact supplied prices and outcomes.'
 };

 // Original examples adapted from patterns in these public GitHub collections.
 // f/prompts.chat: specialist roles tailored to the deliverable.
 // langgptai/LangGPT: separate the goal, context and requested result.
 // dair-ai/Prompt-Engineering-Guide: give a brief example of the desired structure.
 // anthropics/prompt-eng-interactive-tutorial: separate source material with clear labels.
 // GoogleCloudPlatform/generative-ai: establish context and specify the output format.
 const fullPatterns = [
  {kind: 'site', match: /portfolio|портфолио/iu, content: 'Build the journey from specialty to selected work to contact. Give each case study a problem, contribution, design decision and outcome.', visual: 'Show the actual project artifact or a labeled illustrative mockup beside its case study.'},
  {kind: 'site', match: /e.?commerce|online store|интернет.магазин|дүкен/iu, content: 'Organize the experience around discovery, product selection and purchase. Include product details, price or price basis, delivery and a clear purchase action.', visual: 'Show each product in use or at a useful scale and pair the image with a feature the shopper can evaluate.'},
  {kind: 'site', match: /dashboard|бақылау тақтасы|дашборд/iu, content: 'Start with the decision the dashboard supports. Group metrics by priority and show units, time ranges, comparison baselines and useful empty states.', visual: 'Use labeled charts, interface previews and data cards that answer specific decision questions.'},
  {kind: 'site', match: /event|conference|іс.шара|конференци/iu, content: 'Lead with the event promise, date and location, then present the schedule, participants and registration details.', visual: 'Choose venue, speaker or event photos that help attendees understand what to expect.'},
  {kind: 'presentation', match: /қазақ хандығ|қазақстан тарих|казахск\p{L}* ханств|kazakh(?:stan history| khanate)/iu, content: 'Build the story through political context, key people, migration, chronology, consolidation and legacy. Distinguish primary written evidence from later photographs through their dates and captions.', visual: 'Use documented landscapes, archival photographs and museum objects. Identify the place or object, its period and its connection to the page.'},
  {kind: 'presentation', preset: 'editorial_warm', content: 'Sequence the story from setting and participants to turning points, historical evidence and legacy. Attribute disputed dates and interpretations.', visual: 'Pair period-appropriate documentary images or labeled maps with a short explanation of their historical relevance.'},
  {kind: 'presentation', match: /startup|pitch deck|стартап|питч/iu, content: 'Build the pitch around the customer problem, solution, market, business model, evidence of demand and the decision you want from the audience.', visual: 'Use product screens, workflow graphics and clearly labeled charts to illustrate specific claims.'},
  {kind: 'presentation', preset: 'tech_dark', content: 'Move from the problem to a system diagram, practical example, trade-offs and concrete next steps. Define unfamiliar terminology where it first appears.', visual: 'Alternate tool or hardware images with meaningful diagrams and annotated workflow illustrations.'},
  {kind: 'presentation', preset: 'clinical_fresh', content: 'Explain the question, method, results and implications. Give observations their units and context, and distinguish measured effects from interpretation.', visual: 'Use documented subject photographs, labeled charts or diagrams tied to the result being discussed.'},
  {kind: 'presentation', match: /lesson|course|curriculum|сабақ|дәріс|урок|лекци/iu, content: 'Start with a learning objective, explain the concept through a worked example, then give a brief practice task and recap.', visual: 'Choose visuals that explain a step, relationship or common mistake.'}
 ];

 function fullDirection(site, preset, topic) {
  const kind = site ? 'site' : 'presentation';
  const candidates = fullPatterns.filter(pattern => pattern.kind === kind);
  return candidates.find(pattern => pattern.match?.test(topic)) ??
   candidates.find(pattern => pattern.preset === preset.id);
 }
 const limit = (value, size) => {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (text.length <= size) return text;
  const clipped = text.slice(0, size);
  const lastWord = clipped.lastIndexOf(' ');
  return (lastWord > size * 0.75 ? clipped.slice(0, lastWord) : clipped) + '…';
 };
 const xml = value => value.replace(/[&<>]/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'})[char]);
 const list = value => Array.isArray(value) ? value : [];
 const recordList = value => list(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));

 function positiveCount(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : null;
 }

 function requestedCount(text) {
  const match = text.match(/(?:^|[^\d])([1-9]\d{0,2})\s*(?:-\s*)?(?:слайд|бет|страниц|slides?\b|pages?\b)/iu);
  return match ? positiveCount(Number(match[1])) : null;
 }

 function auditContext(audit, kind, tier) {
  if (!audit) return {data: null, title: '', topic: '', domain: '', count: null};
  const editorial = audit.evidence?.editorial;
  const checks = recordList(audit.checks);
  const issues = checks.filter(check => check.status === 'fail').slice(0, 12).map(check => ({
   finding: limit(check.title, 100), evidence: limit(check.evidence, 190), correction: limit(check.recommendation, 220)
  }));
  const goal = limit(audit.user_goal, 650);
  if (kind === 'presentation') {
   const editorialPages = recordList(editorial?.pages);
   const records = editorialPages.length ? editorialPages : recordList(audit.evidence?.page_results);
   const title = limit(editorial?.title, 160);
   const pages = records.map((page, index) => ({
    number: positiveCount(page.page) || index + 1,
    heading: limit(page.heading || list(page.headings)[0], 110),
    facts: list(page.facts).slice(0, 4).map(fact => limit(fact, 100)),
    extract: limit(page.source_text || page.excerpt || page.text_excerpt, EVIDENCE_LIMITS[tier]),
    status: page.text_status || undefined
   }));
   return {
    title, topic: pages.slice(0, 12).map(page => page.heading + ' ' + page.extract).join(' '),
    domain: editorial?.domain || '', count: positiveCount(audit.pages) || positiveCount(pages.length),
    data: {title, goal, orderedObservedPages: pages, confirmedIssues: issues}
   };
  }
  const headings = list(audit.source_headings).slice(0, 25).map(heading => limit(heading?.text || (typeof heading === 'string' ? heading : ''), 125)).filter(Boolean);
  const routes = recordList(audit.site_pages?.pages).map(route => ({
   url: limit(route.url, 300), title: limit(route.title, 120),
   headings: list(route.headings).slice(0, 8).map(heading => limit(heading?.text || (typeof heading === 'string' ? heading : ''), 115)).filter(Boolean),
   evidence: limit(route.excerpt || route.content_text || route.description, EVIDENCE_LIMITS[tier])
  }));
  const title = routes[0]?.title || headings[0] || '';
  return {
   title, topic: [goal, ...headings, ...routes.map(route => route.title), limit(audit.content_text, 2800)].join(' '),
   domain: '', count: null,
   data: {url: audit.source_url || '', goal, observedRoutes: routes, headings,
    extract: limit(audit.content_text, 3 * EVIDENCE_LIMITS[tier]),
    unobservedRoutesExist: Boolean(audit.site_pages?.limited), confirmedIssues: issues}
  };
 }

 function sourceNotes(data) {
  if (!data) return '';
  const lines = [];
  if (data.url) lines.push(data.url);
  for (const page of data.orderedObservedPages || []) {
   const details = [page.heading, ...page.facts, page.extract].filter(Boolean);
   if (details.length) lines.push('Page ' + page.number + ' — ' + details.join(' · '));
  }
  for (const route of data.observedRoutes || []) {
   lines.push([route.title, route.url, ...route.headings, route.evidence].filter(Boolean).join(' · '));
  }
  if (data.headings?.length) lines.push(data.headings.join(' · '));
  if (data.extract) lines.push(data.extract);
  for (const issue of data.confirmedIssues) {
   lines.push([issue.finding, issue.evidence, issue.correction].filter(Boolean).join(' → '));
  }
  return lines.filter(Boolean).join('\n');
 }

 const paletteDirection = {
  editorial_warm: 'For history, culture and literature, use warm parchment for reading surfaces, sand for archival notes, muted copper for dates and labels, and deep navy for headings. Preserve natural archival tones and use the richer accent on sparse section markers.',
  tech_dark: 'For technology and startup topics, use midnight for the canvas, a lifted slate surface for panels, indigo for primary actions and green for positive signals. Use green with a label on metrics, and place code or dense specification blocks on slate with light text.',
  corporate_clean: 'For business, finance and education, give tables and charts a pale canvas, use navy for hierarchy and key actions, and reserve blue for selected comparisons or callouts. Label chart values, units and changes directly.',
  clinical_fresh: 'For science, medicine and ecology, use the light mint canvas to separate observations, the white card color for data, and emerald or teal for sources, results and evidence markers. Use dark forest text over light surfaces for readable explanations.',
  modern_bold: 'For portfolios, marketing and shops, pair warm cream with near-black typography and use raspberry for the primary action, featured products or chapter markers. Keep source imagery and product colors natural.'
 };

 function productionPass(site, pptx, audit) {
  if (site) return [
   'Give each route one visitor goal, a clear entry point and a meaningful next action. Include the main navigation and the core user journey from first visit through completion.',
   'For each key screen, describe section order, component hierarchy and the content it needs. Specify keyboard focus, input labels and the relevant loading, empty, success and error states.',
   'Review the primary journey at mobile and desktop widths. Confirm navigation, responsive layout, image fit and the main interaction in the delivered project.'
  ].join(' ');
  return [
   'Create a page-by-page plan before building the file. For each page give the headline, key takeaway, evidence, layout type and the visual slot allowed by the selected tier.',
   'Build an opening that states the purpose, sequence the evidence, then close with a specific conclusion. Put short explanations beside the visuals and vary page layouts according to the material.',
   pptx ? 'Open the final deck and check slide order, native text editability, picture framing and alignment.'
    : 'Open the final PDF and check the page count, text legibility, image framing and page breaks.',
   audit ? 'Apply the audit findings to the observed pages and keep the verified source facts.' : ''
  ].filter(Boolean).join(' ');
 }

 function visualGuide(level, source, site) {
  const unit = site ? 'section' : 'page';
  if (level === 'short') return 'Use text-only layouts: clear headings, short sections and tables for comparisons.';
  const cadence = level === 'medium'
   ? 'alternate illustrated and text-led ' + unit + 's, starting with an illustration on ' + unit + ' 1 (1, 3, 5, …)'
   : 'illustrate every ' + unit;
  const preferred = source === 'ai' ? 'original AI visuals' : 'real photographs from the web';
  return 'For this ' + (site ? 'website' : 'presentation') + ', ' + cadence + '. Favor ' + preferred +
   ' suited to the topic. Pair each visual with a brief explanation; use photography, illustration or SVG according to your available tools.';
 }

 function build({kind, model = 'chatgpt', tier = 'full', source = 'web', language = 'kk', brief = '', audit = null, outputFormat = null}) {
  const site = kind === 'site';
  const level = Object.hasOwn(EVIDENCE_LIMITS, tier) ? tier : 'full';
  const observed = auditContext(audit, site ? 'site' : 'presentation', level);
  const request = String(brief || '').trim().slice(0, 12000);
  const topic = [request, observed.data?.goal].filter(Boolean).join('\n');
  const preset = designPresets.select({title: observed.title, topic: topic + ' ' + observed.topic, domain: observed.domain});
  const lang = Object.hasOwn(LANGUAGES, language) ? LANGUAGES[language] : LANGUAGES.kk;
  const count = requestedCount(topic) || observed.count || (audit ? null : 8);
  const explicitFormat = outputFormat === 'pdf' || outputFormat === 'pptx';
  const pptx = explicitFormat ? outputFormat === 'pptx' : /\b(?:pptx|powerpoint)\b/i.test(topic);
  const format = pptx ? 'editable PowerPoint presentation' + (!explicitFormat && /\bpdf\b/i.test(topic) ? ' with a PDF export' : '') : 'presentation as a downloadable PDF';
  const deliverable = site ? 'a responsive website' : (pptx ? 'an ' : 'a ') + format + (count ? ' with ' + count + (pptx ? ' slides' : ' pages') : '');
  const direction = level === 'full' ? fullDirection(site, preset, topic + ' ' + observed.title + ' ' + observed.topic) : null;
  const goal = 'As a ' + (site ? 'UX designer and frontend developer' : 'presentation designer and editor') +
   ', ' + (audit ? 'redesign the supplied work as ' : 'create ') + deliverable + ' in ' + lang + '.';
  const palette = Object.entries(preset.palette).map(([name, hex])=>name+' '+hex).join(', ');
  const colorGuide = paletteDirection[preset.id];
  const {heading, body, mono} = preset.fonts;
  const design = palette + '. ' + colorGuide + ' Set body text on the contrasting background or card surface and use accents selectively. Use ' + heading + ' for headings, ' + body + ' for body text' +
   (mono ? ' and ' + mono + ' for code' : '') + ', with Cyrillic Extended (cyrillic-ext) and Noto Sans for Kazakh glyphs.' +
   (level === 'short' ? '' : ' ' + preset.mood) +
   (level !== 'full' ? '' : site
    ? ' Establish a clear hero and primary action, then vary the page with feature cards and comparison sections. Reflow these layouts into a readable single column on phones.'
    : ' Use a clear cover, then rotate photo-and-text spreads, timelines and data layouts as the material calls for them. Place each split-layout visual beside its explanation, within half the page width.');
  const evidence = sourceNotes(observed.data);
  const content = ['Write in natural ' + lang + ' and ground each main point in a fact, date or example.',
   !site && (pptx
    ? 'Deliver a native .pptx with editable text boxes on 13.333 × 7.5 in slides and proportioned image frames.'
    : 'Deliver a print-ready PDF with exact page breaks and crisp, selectable text.'),
   direction?.content ?? subjectFlows[preset.id], site ? 'Guide visitors toward the main action.' : 'Give each page one clear takeaway.',
   level === 'full' && (site
    ? 'Deliver the working project files. Use the requested stack or semantic HTML, CSS and lightweight JavaScript when none is specified.'
    : pptx
     ? 'Use the available presentation tools or PptxGenJS to build the editable deck.'
     : 'Deliver the finished document using your presentation or file tools. Print-ready HTML/CSS is a useful source format when direct file export is unavailable.'),
   level === 'full' && (site
    ? 'Shape each substantive section around a visitor question, one concrete supporting detail and a relevant next action.'
    : 'Shape each page around a specific title, its main claim, supporting evidence and a short visual caption.'),
   level === 'full' && productionPass(site,pptx,Boolean(audit)),
   level === 'full' && 'Cross-check factual claims against the supplied material or credible sources and attach source notes where the reader needs to verify a claim.',
   topic && 'Brief: ' + topic, audit && observed.title && 'Source: ' + observed.title,
   evidence && 'Use these observations to guide the redesign:\n' + evidence].filter(Boolean).join('\n');
  const framing = !site && level !== 'short'
   ? 'Match every image to its container: 16:9 for full-bleed covers, 4:3, 1:1 or 3:4 for split layouts and cards, and 16:9 or 21:9 for wide banners. Center the subject with safe margins around faces, objects and text. Fit the whole image when preserving detail matters.'
   : '';
  const visualCompletion = level === 'full'
   ? site
    ? 'Give informative images meaningful alternative text. Use a consistent visual treatment and reserve each image slot for a specific message.'
    : 'Assign a distinct topic-specific visual to each required page and place a short source note or caption beside it. Reopen the final file and check that all required visual slots are present and readable.'
   : '';
  const visuals = [visualGuide(level, source, site), direction?.visual, framing, visualCompletion].filter(Boolean).join(' ');
  const parts = [['Goal', goal], ['Design', design], ['Content', content], ['Visuals', visuals]];
  return parts.map(([name, value]) => {
   const tag = name.toLowerCase();
   if (model === 'claude') return '<' + tag + '>\n' + xml(value) + '\n</' + tag + '>';
   return (model === 'gemini' ? name.toUpperCase() : '### ' + name) + '\n' + value;
  }).join('\n\n');
 }

 return Object.freeze({build});
});
