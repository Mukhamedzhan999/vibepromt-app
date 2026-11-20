'use strict';

async function requirePdfResponse(response) {
  if (response.ok) return response;
  const problem = await response.json().catch(() => null);
  throw new Error(problem?.error || 'Файлды талдау мүмкін болмады. Қайта көріңіз.');
}

async function readPdfEvents(response, showState) {
  if (!response.body) throw new Error('Талдау нәтижесін оқу мүмкін болмады.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';

  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      pending += decoder.decode(value, {stream: true});
      let boundary;
      while ((boundary = pending.indexOf('\n\n')) !== -1) {
        const entry = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        if (!entry.startsWith('data: ')) continue;
        const state = JSON.parse(entry.slice(6));
        if (state.state === 'done') return {result: state.result, cached: false};
        if (state.state === 'error') throw new Error(state.error);
        showState(state);
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  throw new Error('Талдау нәтижесі толық келмеді. Қайта көріңіз.');
}

async function analyzeVercelPdf(body, showProgress, showState) {
  const file = body.get('file');
  const start = await requirePdfResponse(await fetch('/api/pdf-uploads', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({filename: file.name, size: file.size, prompt: body.get('prompt') || ''}),
    signal: AbortSignal.timeout(30000),
  }));
  const {upload_id, chunk_bytes} = await start.json();
  const path = '/api/pdf-uploads/' + encodeURIComponent(upload_id);

  try {
    for (let offset = 0; offset < file.size; offset += chunk_bytes) {
      const end = Math.min(offset + chunk_bytes, file.size);
      const part = file.slice(offset, end, 'application/octet-stream');
      await requirePdfResponse(await fetch(path + '/' + offset / chunk_bytes, {
        method: 'PUT', body: part, signal: AbortSignal.timeout(120000),
      }));
      const percent = Math.round(100 * end / file.size);
      showProgress(0, 'Жүктелді: ' + percent + '%', Math.round(percent / 4));
    }
    showProgress(1, 'Файл қабылданды. Құжат ашылып жатыр…', 25);
    const response = await requirePdfResponse(await fetch(path + '/analyze', {
      method: 'POST', signal: AbortSignal.timeout(310000),
    }));
    if (response.headers.get('Content-Type')?.includes('application/json')) return await response.json();
    return await readPdfEvents(response, showState);
  } catch (error) {
    await fetch(path, {method: 'DELETE', signal: AbortSignal.timeout(5000)}).catch(() => {});
    throw error;
  }
}
