'use strict';

const fileInput = document.querySelector('#history-file');
const statusText = document.querySelector('#history-status');
const storageKey = 'vibe-saved-audits-v1';

function isAudit(entry) {
  return /^[\w-]{1,99}$/.test(typeof entry?.id === 'string' ? entry.id : '') &&
    typeof entry.source === 'string' && typeof entry.date === 'string' &&
    ['BRIEF', 'URL', 'PDF'].includes(entry.kind) && entry.kind === entry.data?.kind &&
    entry.data.features && typeof entry.data.features === 'object' &&
    entry.data.prompts && typeof entry.data.prompts === 'object';
}

fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  if (!file) return;
  fileInput.disabled = true;
  try {
    if (file.size > 6000000) throw new Error('Тарих файлы тым үлкен.');
    const backup = JSON.parse(await file.text());
    if (backup?.format !== 'vibepromt-audits' || backup.version !== 1 ||
        !Array.isArray(backup.audits) || !backup.audits.every(isAudit)) {
      throw new Error('VibePrompt AI тарих файлын таңдаңыз.');
    }
    const existing = JSON.parse(localStorage.getItem(storageKey) || '[]');
    const merged = new Map(existing.map(entry => [entry.id, entry]));
    for (const entry of backup.audits) {
      if (!merged.has(entry.id)) merged.set(entry.id, entry);
    }
    const ordered = [...merged.values()].sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const serialized = JSON.stringify(ordered);
    if (ordered.length > 12 || serialized.length > 3000000) {
      throw new Error('Браузер тарихында орын жеткіліксіз.');
    }
    localStorage.setItem(storageKey, serialized);
    statusText.textContent = `${ordered.length - existing.length} аудит қосылды.`;
  } catch (error) {
    statusText.textContent = error instanceof SyntaxError
      ? 'Тарих файлын оқу мүмкін болмады.' : error.message;
  } finally {
    fileInput.disabled = false;
    fileInput.value = '';
  }
});
