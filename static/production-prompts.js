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
  const steps = site ? [
   'Translate the brief into an audience, a primary visitor goal and a visible completion state. Plan the routes that serve that goal, then give every route a section order, a clear headline and a next action.',
   'Build a complete first screen: identifiable brand, short navigation, specific headline, one-line value proposition and a primary action that leads to the next step. Follow with substantive sections suited to the brief, such as case studies, product categories, service details, comparisons or a process walkthrough. Finish with a working contact or conversion path and footer.',
   'Build each key section from a headline, a specific detail and useful content the visitor can evaluate. For case studies show the problem, approach and outcome. For products show distinguishing features and supplied terms. For services explain what is included and how to get started. Use concrete sample content labeled as sample when project facts are unavailable.',
   'Write final interface copy. Show the offer or information early, put evidence beside the claim it supports, and make forms, prices, dates and contact details explicit wherever relevant. For an unspecified detail, use a clearly labeled editable field.',
   'Implement the main journey from entry through completion. Give interactive controls working behavior and accessible labels. Where the project calls for them, implement loading, empty, validation, error and success states. Preserve established routes and working actions in a redesign.',
   'Deliver the runnable project with a short launch note. Check the primary journey at phone and desktop widths, keyboard focus order, image fit and completion of the main action. Report the checks you actually ran.'
  ] : [
   'Start with a one-line story for the intended audience. Use the requested page count and structure the story around context, evidence and a concrete conclusion or decision.',
   'Assign every page a distinct job. Draft a claim-led headline, one takeaway, the actual supporting evidence, an appropriate layout and the visual or caption required by the tier. Use a timeline for sequence, a table for exact comparison and a labeled chart for trends.',
   'Write finished text for each page. Prefer short sentences and precise names, dates, units and source notes. Fit the copy to the chosen layout by editing it before reducing type size. The conclusion should answer the question introduced at the beginning.',
   pptx ? 'Build the editable deck, reopen it, and review slide order, editable text boxes, picture framing and layout at normal viewing size.'
    : 'Export the complete PDF, reopen it, and review page count, page breaks, selectable text, readable glyphs and picture framing.'
  ];
  if (audit) steps.splice(1, 0,
   'Use the observations below as source material. For each documented issue, identify the affected page or route, give the observed evidence, and implement a visible correction. Prioritize problems that block reading or the primary action. Keep source facts and working interactions intact, and mark unobserved areas as open questions.');
  return steps.map((step, index) => (index + 1) + '. ' + step).join('\n');
 }

 function visualGuide(level, source, site) {
  const unit = site ? 'section' : 'page';
  if (level === 'short') return 'Use text-only layouts: clear headings, short sections and tables for comparisons.';
  const cadence = level === 'medium'
   ? 'alternate illustrated and text-led ' + unit + 's, starting with an illustration on ' + unit + ' 1 (1, 3, 5, …)'
   : 'illustrate every ' + unit;
  const preferred = source === 'ai' ? 'original AI visuals' : 'real photographs from the web';
  return 'For this ' + (site ? 'website' : 'presentation') + ', ' + cadence + '. Favor ' + preferred +
   ' suited to the topic. Pair each visual with a brief explanation.' +
   (source === 'ai' ? ' Use your available image-generation or illustration tools.' : ' Use illustrations as supporting graphics and label them separately from photographs.');
 }

 function claudeWebsitePhotos(level, topic, isAudit) {
  const placement = level === 'medium'
   ? 'Place one real photo in sections 1, 3, 5 and so on, starting with the hero. Use structured content in intervening sections.'
   : 'Place a real photo in the hero and each topic section. Choose a subject that supports the section and put a concise explanation beside it.';
  const codeSite = /\bgit(?:hub|lab)\b|\bsource code\b|\bversion control\b|бағдарламалау|программирован/iu.test(topic);
  const starter = codeSite
   ? 'For a code-platform hero, use this real photograph of a laptop displaying code where it fits: https://upload.wikimedia.org/wikipedia/commons/1/17/Laptop_Programmcode.jpg . Credit Negative Space (CC0); source: https://commons.wikimedia.org/wiki/File:Laptop_Programmcode.jpg . For an infrastructure section, use https://upload.wikimedia.org/wikipedia/commons/f/fa/Rack_with_varoius_servers.jpg where relevant; credit Aaron Hall (CC BY-SA 2.0): https://commons.wikimedia.org/wiki/File:Rack_with_varoius_servers.jpg . Describe both as illustrative photos of coding or infrastructure.'
   : '';
  return [
   placement,
   isAudit && 'Reuse relevant existing photographs from the audited site when their original file URLs and reuse rights are available; fill remaining sections with topic-specific web photos.',
   'Use Claude web search and image results to choose real photos from the original publisher, a public archive, Wikimedia Commons or a photography collection. Use the direct HTTPS image URL in each HTML img src and link the source page in its caption or credits. Add descriptive alt text, dimensions and responsive cropping.',
   starter,
   'Deliver a standalone index.html, or the equivalent runnable project in the requested stack. When file download is available, save the photos under assets/images/ and reference the local files. When only search or the preview is available, put the direct photo URLs straight in img src so the exported site loads them in a regular browser. A screenshot of the preview or a search-result link is insufficient. An ordinary img element loads a remote image without a client-side fetch or crossorigin attribute.',
   'If a provider link fails, try another relevant photograph or an existing website photo. If one still cannot be sourced, keep that section as a finished text layout, place any blocker in a short delivery note, and preserve the photos in the rest of the site. Keep photo slots out of the layout until they have an actual image source.'
  ].filter(Boolean).join(' ');
 }

 function refreshSavedWebsitePrompt(prompt, options) {
  const {kind, model, tier, source} = options;
  if (kind !== 'site' || model !== 'claude' || tier === 'short' || source !== 'web') return prompt;
  const updated = build(options);
  const visualSection = /<visuals>\n[\s\S]*?\n<\/visuals>$/;
  const replacement = updated.match(visualSection)?.[0];
  return replacement && visualSection.test(prompt) ? prompt.replace(visualSection, () => replacement) : updated;
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
    ? '\nApply the palette as reusable tokens for background, surface, text, actions and focus. Use a fluid page container and comfortable reading widths. Plan a distinct hero composition, detailed content sections, a focused comparison or editorial grid when useful, and a clear closing action. Use a coherent heading scale, 16 px or larger body text, visible keyboard focus and whitespace between sections. Reflow split layouts into a readable single column on phones.'
    : '\nSet a consistent title, body, caption and source hierarchy with generous margins and enough contrast for projection or print. Rotate editorial spreads, timelines and data layouts to fit the topic. In split layouts, keep the visual within half the page width and put its explanation alongside.');
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
   level === 'medium' && (site
    ? 'Write the core pages in visitor order, tie each section to a distinct question and provide working navigation and a clear completion state for the main action.'
    : 'Give every page a distinct headline, one claim and one supporting example. Use the visual pages to show a specific subject and the alternating text-led pages for comparisons or evidence.'),
   level === 'short' && (site
    ? 'Deliver the main visitor journey with a clear headline, a concrete offer and a working next action.'
    : 'Place one claim and its strongest supporting fact on each page. Use comparison tables for exact values and a concise conclusion to tie the pages together.'),
   level === 'full' && 'Cross-check specific factual claims against the supplied material or credible sources. Make assumptions visible, preserve uncertainty where evidence is incomplete and add source notes where readers need to check a claim.',
   topic && 'Project brief\n' + topic, audit && observed.title && 'Source: ' + observed.title,
   evidence && 'Audit observations\n' + evidence].filter(Boolean).join('\n');
  const framing = !site && level !== 'short'
   ? 'Match every image to its container: 16:9 for full-bleed covers, 4:3, 1:1 or 3:4 for split layouts and cards, and 16:9 or 21:9 for wide banners. Center the subject with safe margins around faces, objects and text. Fit the whole image when preserving detail matters.'
   : '';
  const visualCompletion = level === 'full'
   ? site
    ? 'Give the hero and each topic section an identifiable subject, its own image frame, descriptive alt text and a credit when applicable. For web photos, find a real photo of that exact subject and retain its source page. Prefer a local image asset when you can download it. When you can find a verified direct image URL but the chat preview blocks external images, deliver a standalone index.html file using those URLs so the user can open it in a regular browser. Keep credits linked to their source pages. Review every photo slot, and report which images you actually checked. If you cannot locate real photographs, label the missing photo slots explicitly and list the subjects still needed.'
    : 'For every required page, select a distinct subject, choose its frame and pair it with a caption that explains what it shows and why it belongs there. Prefer real, relevant photography when the selected source is the web. Embed the actual assets in the exported PDF or PPTX. Reopen the file and review every page in order. Confirm each required photo is visible, proportionate and accompanied by its caption. If a photo is unavailable, select another relevant source and check its placement before delivery.'
   : '';
  const visuals = (site && model === 'claude' && source === 'web' && level !== 'short'
   ? [claudeWebsitePhotos(level, [topic, observed.title, observed.topic, observed.data?.url].join(' '), Boolean(audit)), direction?.visual]
   : [visualGuide(level, source, site), direction?.visual, framing, visualCompletion]).filter(Boolean).join(' ');
  const parts = [['Goal', goal], ['Design', design], ['Content', content], ['Visuals', visuals]];
  return parts.map(([name, value]) => {
   const tag = name.toLowerCase();
   if (model === 'claude') return '<' + tag + '>\n' + xml(value) + '\n</' + tag + '>';
   return (model === 'gemini' ? name.toUpperCase() : '### ' + name) + '\n' + value;
  }).join('\n\n');
 }

 return Object.freeze({build, refreshSavedWebsitePrompt});
});
