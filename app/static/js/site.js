/*
 * Поведение главной страницы:
 *  - живой пересчёт сметы при любом изменении калькулятора;
 *  - переключение стиля сайта («Классика» / «Яркая»);
 *  - готовые примеры, копирование сметы;
 *  - форма заявки: маска телефона, проверка полей, отправка на сервер.
 * Без JavaScript страница тоже работает: калькулятор пересчитывается кнопкой,
 * а заявка отправляется обычной формой.
 */
(function () {
  'use strict';

  var E = window.SmetaEngine;
  var configEl = document.getElementById('app-config');
  if (!E || !configEl) return;

  var CFG = JSON.parse(configEl.textContent);
  var prices = CFG.prices;
  var demo = !!CFG.demo;
  var root = document.documentElement;
  var pageStart = Date.now();
  var NBSP = '\u00A0';
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  root.classList.add('js');

  // ---------- Мелкие помощники ----------
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  var storage = {
    get: function (key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* хранилище недоступно — не страшно */ } }
  };
  // Создаёт элемент: el('b', {class: 'x'}, ['текст', другой элемент]). Текст всегда через textContent — без риска XSS
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    (children || []).forEach(function (c) { node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return node;
  }
  function scrollToEl(node) {
    if (node && node.scrollIntoView) node.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }
  var toastEl = $('[data-toast]');
  var toastTimer = null;
  function toast(text) {
    if (!toastEl) return;
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 3200);
  }

  // ---------- Стиль сайта ----------
  function setSkin(skin) {
    root.setAttribute('data-skin', skin);
    $$('[data-skin-set]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-skin-set') === skin)); });
    storage.set('smeta-skin', skin);
    // На настоящем сайте запоминаем выбор в cookie, чтобы сервер сразу отдал нужный стиль
    if (!demo) document.cookie = 'skin=' + skin + '; path=/; max-age=31536000; samesite=lax';
  }
  $$('[data-skin-set]').forEach(function (b) {
    b.addEventListener('click', function () { setSkin(b.getAttribute('data-skin-set')); });
  });
  setSkin(root.getAttribute('data-skin') || 'classic');

  // ---------- График работы: «На связи до 17:00» ----------
  function statusText(st) { return st.open ? 'На связи до ' + st.closes + ':00' : 'Перезвоним ' + st.next; }
  function updateStatus() {
    var st = E.workStatus(new Date(), prices.schedule);
    $$('[data-status]').forEach(function (node) {
      node.classList.toggle('is-open', st.open);
      var span = node.querySelector('span');
      if (span) span.textContent = statusText(st);
    });
    var weekend = st.wd === 0 || st.wd === 6;
    var wk = $('[data-sched="weekday"]'), we = $('[data-sched="weekend"]');
    if (wk) wk.classList.toggle('is-today', !weekend);
    if (we) we.classList.toggle('is-today', weekend);
    return st;
  }
  updateStatus();
  setInterval(updateStatus, 60 * 1000);

  // ---------- Калькулятор ----------
  var calc = document.getElementById('calc-form');
  var range = $('#guests');
  var summary = $('#summary');
  var lastEstimate = null;

  function readState() {
    var fd = new FormData(calc);
    return E.normalize({ format: fd.get('f'), guests: fd.get('g'), hours: fd.get('h'), level: fd.get('l'), addons: fd.getAll('a') }, prices);
  }

  function applyState(state) {
    $$('input[name="f"]', calc).forEach(function (i) { i.checked = i.value === state.format; });
    $$('input[name="h"]', calc).forEach(function (i) { i.checked = Number(i.value) === Number(state.hours); });
    $$('input[name="l"]', calc).forEach(function (i) { i.checked = i.value === state.level; });
    $$('input[name="a"]', calc).forEach(function (i) { i.checked = state.addons.indexOf(i.value) > -1; });
    range.value = state.guests;
  }

  function setOut(name, value) {
    $$('[data-out="' + name + '"]').forEach(function (node) { node.textContent = value; });
  }

  function render(fromUser) {
    var state = readState();
    var est = E.estimate(state, prices);
    var g = est.guests;
    lastEstimate = est;

    // Гости: число, слово, заливка шкалы, быстрые кнопки, подсказка про 500+
    range.value = g;
    var pct = (g - prices.guests.min) / (prices.guests.max - prices.guests.min) * 100;
    range.style.setProperty('--p', pct.toFixed(1) + '%');
    setOut('guests', String(g));
    setOut('guests-word', E.plural(g, 'гость', 'гостя', 'гостей'));
    $$('[data-guests]').forEach(function (b) { b.setAttribute('aria-pressed', String(Number(b.getAttribute('data-guests')) === g)); });
    var maxHint = $('[data-guests-max]');
    if (maxHint) maxHint.hidden = g < prices.guests.max;

    // Смета
    setOut('range', E.num(est.low) + ' – ' + E.num(est.high));
    setOut('short', E.shortRange(est.low, est.high));
    setOut('meta', E.describe(est));
    setOut('attach', E.rangeText(est) + '. ' + E.describe(est));
    var sub = $('[data-out="sub"]');
    if (sub) {
      sub.textContent = '';
      sub.appendChild(document.createTextNode('≈ '));
      sub.appendChild(el('b', {}, [E.money(est.total)]));
      sub.appendChild(document.createTextNode(', '));
      sub.appendChild(el('b', {}, [E.money(est.per_guest)]));
      sub.appendChild(document.createTextNode(' на гостя'));
    }
    var list = $('[data-out="lines"]');
    if (list) {
      list.textContent = '';
      est.lines.forEach(function (line) {
        list.appendChild(el('li', {}, [
          el('span', {}, [line.title, el('small', {}, [line.note])]),
          el('b', {}, [E.money(line.sum)])
        ]));
      });
    }

    // Копия параметров в форме заявки (на случай отправки без JavaScript тоже)
    var mirror = { format: est.format.id, guests: g, hours: est.hours, level: est.level.id, addons: est.addons.join(',') };
    $$('[data-mirror]').forEach(function (input) { input.value = mirror[input.getAttribute('data-mirror')]; });

    if (fromUser) {
      if (summary && !reduceMotion) {
        summary.classList.remove('is-updated');
        void summary.offsetWidth; // перезапуск анимации
        summary.classList.add('is-updated');
      }
      // На настоящем сайте смета попадает в адресную строку — ссылкой можно поделиться
      if (!demo && window.history && window.history.replaceState) {
        var params = new URLSearchParams(window.location.search);
        params.set('f', est.format.id);
        params.set('g', String(g));
        params.set('h', String(est.hours));
        params.set('l', est.level.id);
        params.set('a', est.addons.join(','));
        params.delete('calc');
        window.history.replaceState(null, '', window.location.pathname + '?' + params.toString() + window.location.hash);
      }
    }
    return est;
  }

  function setGuests(value) {
    var g = Math.min(prices.guests.max, Math.max(prices.guests.min, Math.round(value)));
    range.value = g;
    render(true);
  }

  if (calc && range) {
    calc.addEventListener('input', function () { render(true); });
    calc.addEventListener('change', function () { render(true); });
    calc.addEventListener('submit', function (e) { e.preventDefault(); render(true); });
    $$('[data-guests-step]').forEach(function (b) {
      b.addEventListener('click', function () {
        var step = prices.guests.step * Number(b.getAttribute('data-guests-step'));
        var current = Number(range.value);
        // Сначала «доводим» до кратного шагу числа, потом шагаем
        var snapped = step > 0 ? Math.floor(current / prices.guests.step) * prices.guests.step : Math.ceil(current / prices.guests.step) * prices.guests.step;
        setGuests(snapped + step);
      });
    });
    $$('[data-guests]').forEach(function (b) {
      b.addEventListener('click', function () { setGuests(Number(b.getAttribute('data-guests'))); });
    });

    // Готовые примеры: подставляем параметры без перезагрузки страницы
    $$('[data-preset]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        var id = link.getAttribute('data-preset');
        var preset = prices.presets.filter(function (p) { return p.id === id; })[0];
        if (!preset) return;
        e.preventDefault();
        applyState(E.normalize(preset.state, prices));
        render(true);
        scrollToEl(document.getElementById('calc'));
        toast('Пример открыт в калькуляторе');
      });
    });

    // В демо-версии (GitHub Pages) параметры сметы можно передать ссылкой: ?f=corporate&g=80
    if (demo && window.location.search) {
      var q = new URLSearchParams(window.location.search);
      if (q.get('f') || q.get('g')) {
        applyState(E.normalize({ format: q.get('f'), guests: q.get('g'), hours: q.get('h'), level: q.get('l'), addons: q.get('a') }, prices));
      }
    }
    render(false);
  }

  // ---------- Скопировать смету ----------
  function estimateText(est) {
    var lines = [
      'Смета: ' + E.describe(est),
      'Ориентир: ' + E.rangeText(est) + ' (≈ ' + E.money(est.total) + ', ' + E.money(est.per_guest) + ' на гостя)',
      ''
    ];
    est.lines.forEach(function (l) { lines.push(l.title + ': ' + E.money(l.sum) + ' (' + l.note + ')'); });
    lines.push('');
    if (!demo) lines.push('Расчёт: ' + window.location.href.split('#')[0]);
    lines.push('Цены ориентировочные. Точную смету подготовит менеджер.');
    return lines.join('\n').replace(/\u00A0/g, ' ');
  }
  function copyFallback(text) {
    var area = el('textarea', { readonly: '', 'aria-hidden': 'true' }, [text]);
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }
  $$('[data-copy-estimate]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (!lastEstimate) return;
      var text = estimateText(lastEstimate);
      var done = function () { toast('Смета скопирована. Вставьте её в чат или письмо'); };
      var fail = function () { toast(copyFallback(text) ? 'Смета скопирована' : 'Не получилось скопировать. Выделите смету и скопируйте вручную'); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fail);
      else fail();
    });
  });

  // ---------- Форма заявки ----------
  var form = document.getElementById('lead-form');
  if (!form) return;
  var successBox = $('[data-success]');
  var statusBox = $('[data-form-status]', form);
  var submitBtn = $('[data-submit]', form);
  var phoneInput = $('#lf-phone');
  var nameInput = $('#lf-name');

  // «Получить точный расчёт» — сразу ставим галочку «Приложить смету» и ставим курсор в поле имени
  $$('[data-attach-estimate]').forEach(function (link) {
    link.addEventListener('click', function () {
      var attach = $('input[name="attach_estimate"]', form);
      if (attach) attach.checked = true;
      setTimeout(function () { if (nameInput && !form.hidden) nameInput.focus({ preventScroll: true }); }, reduceMotion ? 0 : 600);
    });
  });

  // UTM-метки из рекламной ссылки: запоминаем на время визита
  (function rememberUtm() {
    var keys = ['utm_source', 'utm_medium', 'utm_campaign'];
    var q = new URLSearchParams(window.location.search);
    var saved = {};
    try { saved = JSON.parse(window.sessionStorage.getItem('smeta-utm') || '{}'); } catch (e) { saved = {}; }
    keys.forEach(function (k) { if (q.get(k)) saved[k] = q.get(k).slice(0, 100); });
    try { window.sessionStorage.setItem('smeta-utm', JSON.stringify(saved)); } catch (e) { /* нет доступа — ничего */ }
    $$('[data-utm]', form).forEach(function (input) { input.value = saved[input.getAttribute('data-utm')] || input.value || ''; });
  })();

  // Маска телефона: +7 (999) 123-45-67
  function maskPhone(value) {
    var d = String(value || '').replace(/\D/g, '');
    if (!d) return '';
    if (d[0] === '8') d = '7' + d.slice(1);
    if (d[0] !== '7') d = '7' + d;
    var r = d.slice(1, 11);
    var out = '+7';
    if (r.length) out += ' (' + r.slice(0, 3);
    if (r.length >= 3) out += ')';
    if (r.length > 3) out += ' ' + r.slice(3, 6);
    if (r.length > 6) out += '-' + r.slice(6, 8);
    if (r.length > 8) out += '-' + r.slice(8, 10);
    return out;
  }
  var prevPhone = '';
  if (phoneInput) {
    phoneInput.addEventListener('input', function () {
      var raw = phoneInput.value;
      var masked = maskPhone(raw);
      // Стёрли скобку или дефис — стираем вместе с ним и последнюю цифру, иначе маска «залипает»
      if (raw.length < prevPhone.length && masked.replace(/\D/g, '') === prevPhone.replace(/\D/g, '')) {
        masked = maskPhone(prevPhone.replace(/\D/g, '').slice(0, -1));
      }
      phoneInput.value = masked;
      prevPhone = masked;
    });
  }

  // Та же проверка, что на сервере (core/leads.py). Сервер всё равно проверит ещё раз
  function validate(data) {
    var errors = {};
    var tg = String(data.telegram || '').trim().replace(/^(https?:\/\/)?(t\.me|telegram\.me)\//i, '').replace(/^@/, '');
    if (!data.name || data.name.trim().length < 2) errors.name = 'Укажите имя';
    if (String(data.phone || '').replace(/\D/g, '').length !== 11) errors.phone = 'Введите номер полностью';
    if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.email.trim())) errors.email = 'Проверьте адрес почты';
    if (tg && !/^[A-Za-z0-9_]{5,32}$/.test(tg)) errors.telegram = 'Например: @username';
    if (data.channel === 'telegram' && !tg) errors.telegram = errors.telegram || 'Укажите Telegram, чтобы мы написали туда';
    if (data.channel === 'email' && !data.email) errors.email = errors.email || 'Укажите почту, чтобы мы ответили туда';
    if (!data.consent) errors.consent = 'Нужно согласие на обработку данных';
    return errors;
  }

  function showErrors(errors) {
    var first = null;
    $$('[data-field]', form).forEach(function (field) {
      var name = field.getAttribute('data-field');
      var msg = errors[name];
      var errEl = $('.field__err', field);
      var input = $('input, textarea', field);
      field.classList.toggle('has-error', !!msg);
      if (errEl) { errEl.textContent = msg || ''; errEl.hidden = !msg; }
      if (input) input.setAttribute('aria-invalid', msg ? 'true' : 'false');
      if (msg && !first) first = input;
    });
    if (first) first.focus();
  }
  // Ошибку у поля убираем, как только человек начал его исправлять
  form.addEventListener('input', function (e) {
    var field = e.target.closest && e.target.closest('[data-field]');
    if (field && field.classList.contains('has-error')) {
      field.classList.remove('has-error');
      var errEl = $('.field__err', field);
      if (errEl) errEl.hidden = true;
      e.target.setAttribute('aria-invalid', 'false');
    }
  });

  function collect() {
    var fd = new FormData(form);
    var data = {
      name: (fd.get('name') || '').trim(),
      phone: fd.get('phone') || '',
      email: (fd.get('email') || '').trim(),
      telegram: (fd.get('telegram') || '').trim(),
      channel: fd.get('channel') || 'phone',
      call_time: fd.get('call_time') || 'asap',
      message: (fd.get('message') || '').trim(),
      consent: !!fd.get('consent'),
      attach_estimate: !!fd.get('attach_estimate'),
      website: fd.get('website') || '',
      elapsed_ms: Date.now() - pageStart,
      utm_source: fd.get('utm_source') || '',
      utm_medium: fd.get('utm_medium') || '',
      utm_campaign: fd.get('utm_campaign') || ''
    };
    if (data.attach_estimate && calc) data.estimate = readState();
    return data;
  }

  function setBusy(busy) {
    if (!submitBtn) return;
    submitBtn.disabled = busy;
    submitBtn.textContent = busy ? 'Отправляем…' : 'Заказать звонок';
  }
  function setFormStatus(text) {
    if (!statusBox) return;
    statusBox.textContent = text || '';
    statusBox.hidden = !text;
  }
  function showSuccess(message) {
    form.hidden = true;
    var text = $('[data-success-text]', successBox);
    if (text) text.textContent = message;
    successBox.hidden = false;
    successBox.focus();
  }
  function thanksText() {
    var st = E.workStatus(new Date(), prices.schedule);
    return st.open
      ? 'Менеджер перезвонит в течение ' + CFG.responseMinutes + NBSP + 'минут.'
      : 'Сейчас мы не на связи. Перезвоним ' + st.next + ' по московскому времени.';
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    setFormStatus('');
    var data = collect();
    var errors = validate(data);
    if (Object.keys(errors).length) { showErrors(errors); return; }
    showErrors({});

    // Демо-версия: заявка остаётся в браузере и появляется в «Панели менеджера»
    if (demo) {
      var est = data.estimate ? E.estimate(data.estimate, prices) : null;
      if (window.SmetaDemo) window.SmetaDemo.addLead(data, est);
      showSuccess(thanksText() + ' Это демо: заявка сохранена только в вашем браузере. Откройте «Панель менеджера», чтобы увидеть её глазами агентства.');
      return;
    }

    setBusy(true);
    fetch(CFG.endpoints.leads, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(data)
    })
      .then(function (res) { return res.json().then(function (body) { return { status: res.status, body: body }; }); })
      .then(function (r) {
        setBusy(false);
        if (r.body.ok) { showSuccess(r.body.message || thanksText()); return; }
        if (r.status === 400 && r.body.errors) { showErrors(r.body.errors); setFormStatus(r.body.message || 'Проверьте поля формы'); return; }
        setFormStatus(r.body.message || 'Не удалось отправить заявку. Попробуйте ещё раз.');
      })
      .catch(function () {
        setBusy(false);
        setFormStatus('Нет связи с сервером. Проверьте интернет или позвоните нам.');
      });
  });

  var again = $('[data-again]');
  if (again) {
    again.addEventListener('click', function () {
      ['name', 'phone', 'email', 'telegram', 'message'].forEach(function (n) { var i = form.elements[n]; if (i) i.value = ''; });
      prevPhone = '';
      successBox.hidden = true;
      form.hidden = false;
      if (nameInput) nameInput.focus();
    });
  }

  // Ссылка на политику в демо-версии раскрывает текст внизу страницы
  $$('[data-open-privacy]').forEach(function (link) {
    link.addEventListener('click', function (e) {
      var box = document.getElementById('privacy');
      if (!box) return;
      e.preventDefault();
      box.open = true;
      scrollToEl(box);
    });
  });
})();
