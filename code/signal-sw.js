/* No caching: authentication and API responses stay on the network. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let packet = {title: 'Drown Guardian · 테스트', body: '테스트 신호가 도착했습니다.'};
  try { if (event.data) packet = event.data.json(); } catch { /* Show a visible fallback. */ }
  event.waitUntil(self.registration.showNotification(packet.title, {
    body: packet.body, tag: `signal-test-${packet.id || Date.now()}`,
    data: {url: '/signal-test.html'}, vibrate: [200, 100, 200]
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    const existing = clients.find(client => new URL(client.url).pathname === '/signal-test.html');
    if (existing) return existing.focus();
    return self.clients.openWindow('/signal-test.html');
  })());
});
