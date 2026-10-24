/*
 * Только для демо-версии: «Панель менеджера».
 * Показывает, как агентство получает заявку: карточку в Telegram с кнопками
 * статусов и строку в CRM. В настоящем проекте это делают бот и сервер,
 * здесь всё живёт в браузере (localStorage) и видно только вам.
 */
(function () {
  'use strict';

  var E = window.SmetaEngine;
  var configEl = document.getElementById('app-config');
  if (!E || !configEl) return;
  var CFG = JSON.parse(configEl.textContent);
  if (!CFG.demo) return;
  var prices = CFG.prices;
  var KEY = 'smeta-demo-leads';

  var STATUSES = {
    new: { title: 'Новая', emoji: '🆕', action: 'Новая' },
    in_progress: { title: 'В работе', emoji: '🟡', action: 'Взял в работу' },
    quoted: { title: 'Смета отправлена', emoji: '📄', action: 'Смета отправлена' },
    won: { title: 'Договор', emoji: '✅', action: 'Договор' },
    lost: { title: 'Отказ', emoji: '✖️', action: 'Отказ' }
  };
  var CHANNELS = { phone: 'звонок', telegram: 'Telegram', email: 'почта' };
  var CALL_TIMES = { asap: 'как можно скорее', morning: 'утром, 8–12', day: 'днём, 12–17', weekend: 'в выходной' };

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    (children || []).forEach(function (c) { if (c != null) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return node;
  }
  function load() { try { return JSON.parse(window.localStorage.getItem(KEY)) || []; } catch (e) { return []; } }
  function save(list) { try { window.localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) { /* без хранилища заявки живут до перезагрузки */ } }
  function fmtTime(ts) {
    var d = new Date(ts);
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function formatPhone(p) {
    var d = String(p || '').replace(/\D/g, '');
    if (d.length === 11) return '+7 (' + d.slice(1, 4) + ') ' + d.slice(4, 7) + '-' + d.slice(7, 9) + '-' + d.slice(9, 11);
    return p;
  }

  // Три примера, чтобы панель не была пустой. Помечены как примеры
  function examples() {
    var now = Date.now();
    var make = function (id, presetIndex, status, hoursAgo, person) {
      var preset = prices.presets[presetIndex];
      return {
        id: id, example: true, status: status, created: now - hoursAgo * 3600 * 1000,
        name: person.name, phone: person.phone, telegram: person.telegram || '', email: '',
        channel: person.channel, call_time: person.call_time, message: person.message || '',
        estimate: E.estimate(E.normalize(preset.state, prices), prices),
        actor: status === 'new' ? '' : 'Анна (Telegram)'
      };
    };
    return [
      make(40, 1, 'new', 0.4, { name: 'Мария (пример)', phone: '+79000000040', channel: 'phone', call_time: 'asap', message: 'Дата 20 декабря, площадка своя' }),
      make(39, 0, 'in_progress', 5, { name: 'Олег (пример)', phone: '+79000000039', telegram: '@example_oleg', channel: 'telegram', call_time: 'day' }),
      make(38, 2, 'won', 30, { name: 'Ирина (пример)', phone: '+79000000038', channel: 'phone', call_time: 'morning', message: 'Нужен трансфер из Москвы' })
    ];
  }

  var mine = load();
  var samples = examples();
  function all() { return mine.concat(samples).sort(function (a, b) { return b.id - a.id; }); }

  // ---------- Карточка в «Telegram» (повторяет core/cards.py) ----------
  function cardNodes(lead) {
    var st = STATUSES[lead.status];
    var est = lead.estimate;
    var rows = [];
    rows.push(el('p', {}, [st.emoji + ' ', el('span', { class: 'tg-strong' }, ['Заявка №' + lead.id]), ' · ' + st.title, lead.example ? ' ' : null, lead.example ? el('span', { class: 'tg-tag' }, ['пример']) : null]));
    if (est) {
      rows.push(el('p', {}, [
        el('span', { class: 'tg-strong' }, [est.format.title]),
        ', «' + est.level.title + '», ' + E.guestsNom(est.guests) + ', ' + E.hoursLabel(est.hours)
      ]));
      rows.push(el('p', {}, ['💰 ', el('span', { class: 'tg-strong' }, [E.rangeText(est)])]));
      var addons = est.lines.slice(1).map(function (l) { return l.title.toLowerCase(); }).join(', ');
      rows.push(el('p', { class: 'tg-muted' }, ['≈ ' + E.money(est.total) + ' · ' + E.money(est.per_guest) + ' на гостя. Услуги: ' + (addons || 'только организация')]));
    } else {
      rows.push(el('p', {}, ['💰 Смету не приложил, нужен расчёт по звонку']));
    }
    var contacts = ['👤 ' + lead.name, '📞 ' + formatPhone(lead.phone)];
    if (lead.telegram) contacts.push('✈️ ' + lead.telegram);
    if (lead.email) contacts.push('📧 ' + lead.email);
    contacts.push('🕐 Связаться: ' + CHANNELS[lead.channel] + ', ' + CALL_TIMES[lead.call_time]);
    rows.push(el('p', { class: 'tg-lines' }, [contacts.join('\n')]));
    if (lead.message) rows.push(el('p', {}, ['📝 «' + lead.message + '»']));
    if (lead.status !== 'new' && lead.actor) rows.push(el('p', { class: 'tg-muted' }, ['Статус «' + st.title + '»: ' + lead.actor]));
    return rows;
  }

  function keyboard(lead) {
    var box = el('div', { class: 'tg-msg__keys' });
    var btn = function (code, text, wide) {
      var current = lead.status === code;
      var b = el('button', { type: 'button', 'aria-pressed': String(current) }, [current ? '✓ ' + STATUSES[code].title : (text || STATUSES[code].emoji + ' ' + STATUSES[code].action)]);
      if (wide) b.className = 'wide';
      b.addEventListener('click', function () { setStatus(lead.id, code); });
      box.appendChild(b);
    };
    if (lead.status === 'won' || lead.status === 'lost') {
      btn('in_progress', '↩️ Вернуть в работу', true);
    } else {
      btn('in_progress'); btn('quoted'); btn('won'); btn('lost');
    }
    return box;
  }

  // ---------- Отрисовка панели ----------
  var dialog = document.getElementById('manager');
  var feed = $('[data-mgr-feed]');
  var rowsBox = $('[data-mgr-rows]');
  var kpis = $('[data-mgr-kpis]');
  var badges = $$('[data-mgr-badge]');

  function renderFeed() {
    if (!feed) return;
    feed.textContent = '';
    all().slice().reverse().forEach(function (lead) {  // в чате старые сообщения сверху
      feed.appendChild(el('article', { class: 'tg-msg', 'aria-label': 'Заявка №' + lead.id }, [
        el('div', { class: 'tg-msg__bubble' }, cardNodes(lead)),
        keyboard(lead),
        el('p', { class: 'tg-msg__time' }, ['Бот агентства · ' + fmtTime(lead.created)])
      ]));
    });
  }

  function renderCrm() {
    var list = all();
    var withEst = list.filter(function (l) { return l.estimate; });
    var avg = withEst.length ? withEst.reduce(function (t, l) { return t + l.estimate.total; }, 0) / withEst.length : 0;
    var count = function (code) { return list.filter(function (l) { return l.status === code; }).length; };
    if (kpis) {
      kpis.textContent = '';
      [['Всего заявок', String(list.length)], ['Новые', String(count('new'))], ['В работе', String(count('in_progress') + count('quoted'))],
        ['Договоры', String(count('won'))], ['Средняя смета', avg ? E.money(Math.round(avg / 1000) * 1000) : '—']]
        .forEach(function (k) { kpis.appendChild(el('div', { class: 'kpi' }, [el('small', {}, [k[0]]), el('b', {}, [k[1]])])); });
    }
    if (rowsBox) {
      rowsBox.textContent = '';
      list.forEach(function (lead) {
        var est = lead.estimate;
        rowsBox.appendChild(el('tr', {}, [
          el('td', { class: 'num' }, [String(lead.id)]),
          el('td', {}, [lead.name, el('br'), el('small', {}, [formatPhone(lead.phone)])]),
          el('td', {}, [est ? est.format.title + ', ' + E.guestsNom(est.guests) : 'без сметы']),
          el('td', { class: 'num' }, [est ? E.shortRange(est.low, est.high) : '—']),
          el('td', {}, [el('span', { class: 'pill pill--' + lead.status }, [STATUSES[lead.status].title])])
        ]));
      });
    }
  }

  function renderBadge() {
    var fresh = all().filter(function (l) { return l.status === 'new'; }).length;
    badges.forEach(function (badge) {
      badge.textContent = String(fresh);
      badge.hidden = fresh === 0;
    });
  }

  function renderAll() { renderFeed(); renderCrm(); renderBadge(); }

  function setStatus(id, code) {
    var lead = all().filter(function (l) { return l.id === id; })[0];
    if (!lead || lead.status === code) return;
    lead.status = code;
    lead.actor = 'Вы (Telegram, ' + fmtTime(Date.now()) + ')';
    save(mine);
    renderAll();
  }

  // ---------- Публичный метод: форма на странице добавляет заявку ----------
  window.SmetaDemo = {
    addLead: function (data, est) {
      var maxId = all().reduce(function (m, l) { return Math.max(m, l.id); }, 40);
      var lead = {
        id: maxId + 1, example: false, status: 'new', created: Date.now(),
        name: data.name, phone: '+' + String(data.phone).replace(/\D/g, ''),
        telegram: data.telegram ? '@' + data.telegram.replace(/^(https?:\/\/)?(t\.me|telegram\.me)\//i, '').replace(/^@/, '') : '',
        email: data.email, channel: data.channel, call_time: data.call_time, message: data.message,
        estimate: est, actor: ''
      };
      mine.push(lead);
      save(mine);
      renderAll();
      return lead;
    }
  };

  // ---------- Открытие, вкладки, удаление ----------
  // Кнопок открытия две: плавающая (ПК) и в верхней полосе (телефон)
  var openBtns = $$('[data-mgr-open]');
  if (openBtns.length && dialog) {
    openBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        renderAll();
        if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
        var feedEnd = feed && feed.lastElementChild;
        if (feedEnd && feedEnd.scrollIntoView) feedEnd.scrollIntoView({ block: 'end' });
      });
    });
    $('[data-mgr-close]').addEventListener('click', function () { dialog.close ? dialog.close() : dialog.removeAttribute('open'); });
    dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });  // клик по затемнению
  }
  $$('[data-mgr-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      var name = tab.getAttribute('data-mgr-tab');
      $$('[data-mgr-tab]').forEach(function (t) { t.setAttribute('aria-selected', String(t === tab)); });
      $$('[data-mgr-pane]').forEach(function (p) { p.hidden = p.getAttribute('data-mgr-pane') !== name; });
    });
  });
  var resetBtn = $('[data-mgr-reset]');
  var armed = null;
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      if (!armed) {  // подтверждение прямо в кнопке: второй клик удаляет
        resetBtn.textContent = 'Нажмите ещё раз, чтобы удалить';
        armed = setTimeout(function () { armed = null; resetBtn.textContent = 'Удалить мои заявки'; }, 4000);
        return;
      }
      clearTimeout(armed);
      armed = null;
      mine = [];
      samples = examples();
      save(mine);
      resetBtn.textContent = 'Удалить мои заявки';
      renderAll();
    });
  }

  renderBadge();
})();
