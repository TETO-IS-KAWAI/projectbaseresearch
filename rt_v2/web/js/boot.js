/* boot.js — 첫 페인트 전에 테마 적용 (깜빡임 방지)
   CSP 가 인라인 스크립트를 막기 때문에 별도 파일로 둔다. */
(function () {
  var q = new URLSearchParams(location.search).get('theme');
  if (q === 'light' || q === 'dark') document.documentElement.dataset.theme = q;
})();
