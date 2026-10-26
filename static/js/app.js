document.addEventListener('DOMContentLoaded', function () {

  /* ---------- Tun / kun rejimi ---------- */
  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var root = document.documentElement;
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
    });
  }

  /* ---------- Parolni ko'rsatish / yashirish ---------- */
  function eye(name) { return '<svg class="icon"><use href="#' + name + '"/></svg>'; }

  document.querySelectorAll('input[type="password"]').forEach(function (input) {
    var wrap = document.createElement('div');
    wrap.className = 'pw-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-toggle';
    btn.setAttribute('aria-label', "Parolni ko'rsatish");
    btn.innerHTML = eye('i-eye');
    wrap.appendChild(btn);

    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.innerHTML = eye(show ? 'i-eye-off' : 'i-eye');
      btn.setAttribute('aria-label', show ? 'Parolni yashirish' : "Parolni ko'rsatish");
    });
  });

  /* ---------- Bildirishnomalar sonini yangilash ---------- */
  var badge = document.getElementById('notif-badge');
  if (badge) {
    setInterval(function () {
      if (document.hidden) return;
      fetch(badge.dataset.url, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          badge.textContent = d.count > 99 ? '99+' : d.count;
          badge.hidden = !d.count;
        })
        .catch(function () {});
    }, 30000);
  }

  /* ---------- Hero video ---------- */
   /* ---------- Hero video ---------- */
  var hero = document.querySelector('.hero-video');
  if (hero) {
    hero.muted = true;
    hero.addEventListener('playing', function () {
      hero.classList.add('ready');
      hero.parentElement.classList.add('video-on');
    });
    var started = hero.play();
    if (started && started.catch) started.catch(function () {});
  }

  /* ---------- Bo'sh vaqtlarni yuklash ---------- */
  var input = document.getElementById('date-input');
  var box = document.getElementById('slots');
  if (!input || !box) return;

  function loadSlots() {
    box.innerHTML = '<p class="muted small">Yuklanmoqda...</p>';
    fetch(input.dataset.url + '?date=' + encodeURIComponent(input.value))
      .then(function (r) { return r.text(); })
      .then(function (html) { box.innerHTML = html; })
      .catch(function () {
        box.innerHTML = '<p class="muted small">Xatolik yuz berdi. Qayta urinib ko\'ring.</p>';
      });
  }

  input.addEventListener('change', loadSlots);
  loadSlots();
});