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

 function build({kind, model = 'chatgpt', tier = 'full', source = 'web', language = 'kk', brief = '', audit = null}) {
  const site = kind === 'site';
  const level = Object.hasOwn(EVIDENCE_LIMITS, tier) ? tier : 'full';
  const observed = auditContext(audit, site ? 'site' : 'presentation', level);
  const request = String(brief || '').trim().slice(0, 12000);
  const topic = [request, observed.data?.goal].filter(Boolean).join('\n');
  const preset = designPresets.select({title: observed.title, topic: topic + ' ' + observed.topic, domain: observed.domain});
  const lang = Object.hasOwn(LANGUAGES, language) ? LANGUAGES[language] : LANGUAGES.kk;
  const count = requestedCount(topic) || observed.count || (audit ? null : 8);
  const pptx = /\b(?:pptx|powerpoint)\b/i.test(topic);
  const format = pptx ? 'editable PowerPoint presentation' + (/\bpdf\b/i.test(topic) ? ' with a PDF export' : '') : 'presentation as a downloadable PDF';
  const deliverable = site ? 'a responsive website' : (pptx ? 'an ' : 'a ') + format + (count ? ' with ' + count + (pptx ? ' slides' : ' pages') : '');
  const goal = 'As a ' + (site ? 'UX designer and frontend developer' : 'presentation designer and editor') +
   ', ' + (audit ? 'redesign the supplied work as ' : 'create ') + deliverable + ' in ' + lang + '.';
  const palette = Object.entries(preset.palette).map(([name, hex]) => name + ' ' + hex).join(', ');
  const {heading, body, mono} = preset.fonts;
  const design = palette + '. Use ' + heading + ' for headings, ' + body + ' for body text' +
   (mono ? ' and ' + mono + ' for code' : '') + ', with Cyrillic Extended (cyrillic-ext) and Noto Sans for Kazakh glyphs.' +
   (level === 'short' ? '' : ' ' + preset.mood);
  const evidence = sourceNotes(observed.data);
  const content = ['Write in natural ' + lang + ' and ground each main point in a fact, date or example.',
   subjectFlows[preset.id], site ? 'Guide visitors toward the main action.' : 'Give each page one clear takeaway.',
   topic && 'Brief: ' + topic, audit && observed.title && 'Source: ' + observed.title,
   evidence && 'Use these observations to guide the redesign:\n' + evidence].filter(Boolean).join('\n');
  const parts = [['Goal', goal], ['Design', design], ['Content', content], ['Visuals', visualGuide(level, source, site)]];
  return parts.map(([name, value]) => {
   const tag = name.toLowerCase();
   if (model === 'claude') return '<' + tag + '>\n' + xml(value) + '\n</' + tag + '>';
   return (model === 'gemini' ? name.toUpperCase() : '### ' + name) + '\n' + value;
  }).join('\n\n');
 }

 return Object.freeze({build});
});