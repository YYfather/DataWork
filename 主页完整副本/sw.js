const CACHE_NAME = 'homepage-v3';
const STATIC_ASSETS = [
  './',
  './index.html',
  './avatar.jpg',
  './manifest.json',
  './shared/theme.css',
  './shared/theme.js',
  './shared/utils.js',
  './shared/avatar-crop.js'
];

// 子应用路径列表 - 不拦截这些路径下的请求
const SUB_APP_PATHS = ['/vault/', '/english/', '/reader/', '/wiki/', '/reasonix/'];

// Install - 立即激活
self.addEventListener('install', function(event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) { return cache.addAll(STATIC_ASSETS); })
  );
});

// Activate - 清理旧缓存，立即接管
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    }).then(function() { return self.clients.claim(); })
  );
});

// Fetch
self.addEventListener('fetch', function(event) {
  // 只处理 GET 请求
  if (event.request.method !== 'GET') return;

  // 只处理 http/https 协议，忽略 chrome-extension、moz-extension 等
  var url = event.request.url;
  if (!url.startsWith('http://') && !url.startsWith('https://')) return;

  // 解析 URL 路径
  var urlObj = new URL(url);
  var pathname = urlObj.pathname;

  // 子应用请求：不拦截，直接放行
  for (var i = 0; i < SUB_APP_PATHS.length; i++) {
    if (pathname.includes(SUB_APP_PATHS[i])) {
      return;
    }
  }

  // API 请求：永远从网络获取
  if (url.includes('api') && url.endsWith('.php')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // HTML 页面：网络优先
  if (event.request.destination === 'document' || url.endsWith('.html')) {
    event.respondWith(
      fetch(event.request)
        .then(function(response) {
          if (response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(c) { c.put(event.request, clone); });
          }
          return response;
        })
        .catch(function() { return caches.match(event.request); })
    );
    return;
  }

  // 其他静态资源：缓存优先
  event.respondWith(
    caches.match(event.request).then(function(cached) {
      if (cached) return cached;
      return fetch(event.request).then(function(response) {
        if (response.ok) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(c) { c.put(event.request, clone); });
        }
        return response;
      }).catch(function() {
        // 网络请求失败，返回一个简单的错误响应
        return new Response('Network error', { status: 503, statusText: 'Service Unavailable' });
      });
    })
  );
});
