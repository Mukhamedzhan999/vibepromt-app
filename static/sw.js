self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
    if (event.request.mode !== 'navigate') return;
    event.respondWith(fetch(event.request).catch(() => new Response(
        'VibePrompt AI серверіне қосылу мүмкін болмады. Интернет байланысын тексеріп, қайта көріңіз.',
        {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}}
    )));
});
