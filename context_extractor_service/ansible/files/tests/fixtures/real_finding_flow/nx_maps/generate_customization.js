const https = require('https');

function fetch(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    if (maxRedirects <= 0) {
      return reject(new Error('Too many redirects'));
    }
    const protocol = url.startsWith('https') ? https : require('http');
    protocol.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        const redirectUrl = new URL(res.headers.location, url).href;
        console.log(`  → Following redirect to ${redirectUrl}`);
        return resolve(fetch(redirectUrl, maxRedirects - 1));
      }
    });
  });
}
