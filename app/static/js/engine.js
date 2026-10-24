/*
 * Движок сметы для браузера — точная копия core/pricing.py.
 * Нужен, чтобы цена пересчитывалась мгновенно, без запроса к серверу.
 * Сервер всё равно пересчитывает смету сам, когда приходит заявка,
 * поэтому подделать цену из браузера нельзя.
 * Совпадение с Python проверяет scripts/check_js_engine.mjs (запускается в CI).
 */
(function (root) {
  'use strict';

  var NBSP = '\u00A0';

  // Math.round в JS и так округляет половинки вверх — как js_round() в Python
  function round(x) { return Math.round(x); }

  // 1 гость, 2 гостя, 5 гостей
  function plural(n, one, few, many) {
    n = Math.abs(n) % 100;
    var last = n % 10;
    if (n > 10 && n < 20) return many;
    if (last > 1 && last < 5) return few;
    if (last === 1) return one;
    return many;
  }

  // 1250000 -> «1 250 000»
  function num(n) {
    return String(round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  }
  function money(n) { return num(n) + NBSP + '₽'; }
  function guestsNom(n) { return n + NBSP + plural(n, 'гость', 'гостя', 'гостей'); }
  function guestsGen(n) { return n + NBSP + plural(n, 'гостя', 'гостей', 'гостей'); }
  function hoursLabel(h) { return h + NBSP + plural(h, 'час', 'часа', 'часов'); }

  // «430–540 тыс. ₽» или «1,2–1,5 млн ₽»
  function shortRange(lo, hi) {
    if (hi < 1000000) return round(lo / 1000) + '–' + round(hi / 1000) + NBSP + 'тыс.' + NBSP + '₽';
    var mln = function (v) { return (v / 1000000).toFixed(1).replace('.', ','); };
    return mln(lo) + '–' + mln(hi) + NBSP + 'млн' + NBSP + '₽';
  }

  function round500(v) { return round(v / 500) * 500; }

  function nice(v) {
    var step = v < 100000 ? 1000 : v < 500000 ? 5000 : v < 2000000 ? 10000 : 50000;
    return round(v / step) * step;
  }

  function addonPrice(rule, levelIndex) {
    return Array.isArray(rule.price) ? rule.price[levelIndex] : rule.price;
  }

  function addonHint(rule) {
    return 'от ' + money(rule.base || addonPrice(rule, 0)) + (rule.hint_unit || '');
  }

  // Сколько единиц услуги: [количество для цены, число групп для подписи]
  function units(rule, g, h) {
    var unit = rule.unit || 'event';
    if (unit === 'event') return [1, 1];
    if (unit === 'guest') return [Math.max(0, g - (rule.included || 0)), 1];
    if (unit === 'hour') return [h, 1];
    var groups = Math.max(rule.min_groups || 1, Math.ceil(g / rule.group_size));
    if (unit === 'group') return [groups, groups];
    if (unit === 'staff_hour') return [groups * h, groups];
    throw new Error('Неизвестная единица услуги: ' + unit);
  }

  function discount(rule, g) {
    var list = rule.discounts || [];
    for (var i = 0; i < list.length; i++) {
      if (g >= list[i][0]) return list[i][1];
    }
    return 0;
  }

  function note(rule, levelIndex, g, h, groups, disc) {
    var tpl = rule.note || '';
    if (Array.isArray(tpl)) return tpl[levelIndex];
    var values = {
      h: h,
      g: g,
      guests: guestsGen(g),
      n: groups,
      n_word: rule.words ? plural(groups, rule.words[0], rule.words[1], rule.words[2]) : '',
      discount: disc ? ' · скидка ' + round(disc * 100) + '%' : ''
    };
    return tpl.replace(/\{(\w+)\}/g, function (m, key) { return key in values ? String(values[key]) : m; });
  }

  // Приводит параметры к понятному виду (как normalize_params в Python)
  function normalize(raw, prices) {
    raw = raw || {};
    var d = prices.defaults;
    var guests = Number(raw.guests != null ? raw.guests : d.guests);
    if (!isFinite(guests)) guests = d.guests;
    var hours = parseInt(raw.hours != null ? raw.hours : d.hours, 10);
    if (!isFinite(hours)) hours = d.hours;
    var addons = raw.addons != null ? raw.addons : d.addons;
    if (typeof addons === 'string') addons = addons.split(',').filter(Boolean);
    var known = {};
    prices.addons.forEach(function (a) { known[a.id] = true; });
    var seen = {};
    addons = (Array.isArray(addons) ? addons : []).filter(function (a) {
      if (typeof a !== 'string' || !known[a] || seen[a]) return false;
      seen[a] = true;
      return true;
    });
    return {
      format: String(raw.format || d.format),
      guests: guests,
      hours: hours,
      level: String(raw.level || d.level),
      addons: addons
    };
  }

  function estimate(params, prices) {
    var fmt = null, i;
    for (i = 0; i < prices.formats.length; i++) if (prices.formats[i].id === params.format) fmt = prices.formats[i];
    if (!fmt) for (i = 0; i < prices.formats.length; i++) if (prices.formats[i].id === prices.defaults.format) fmt = prices.formats[i];

    var levelIndex = 0;
    for (i = 0; i < prices.levels.length; i++) if (prices.levels[i].id === params.level) levelIndex = i;
    var level = prices.levels[levelIndex];

    var duration = null;
    for (i = 0; i < prices.hours.length; i++) if (prices.hours[i].h === params.hours) duration = prices.hours[i];
    if (!duration) for (i = 0; i < prices.hours.length; i++) if (prices.hours[i].h === prices.defaults.hours) duration = prices.hours[i];

    var cfg = prices.guests;
    var g = Math.min(cfg.max, Math.max(cfg.min, round(params.guests)));
    var scale = g <= cfg.base ? 1 : Math.pow(g / cfg.base, cfg.exponent);
    var baseSum = Math.max(fmt.min, (fmt.min + (fmt.max - fmt.min) * level.pos) * scale * duration.k);

    var lines = [{ id: 'base', title: 'Организация и сценарий', note: fmt.title + ' · ' + level.title, sum: round500(baseSum) }];
    var chosen = {};
    (params.addons || []).forEach(function (a) { chosen[a] = true; });

    prices.addons.forEach(function (rule) {
      if (!chosen[rule.id]) return;
      var u = units(rule, g, duration.h);
      var total = (rule.base || 0) + addonPrice(rule, levelIndex) * u[0];
      if (rule.level_mult) total *= level.mult;
      var disc = discount(rule, g);
      total *= 1 - disc;
      total = Math.max(rule.min || 0, total);
      lines.push({ id: rule.id, title: rule.title, note: note(rule, levelIndex, g, duration.h, u[1], disc), sum: round500(total) });
    });

    var total = lines.reduce(function (t, l) { return t + l.sum; }, 0);
    return {
      format: { id: fmt.id, title: fmt.title },
      level: { id: level.id, title: level.title },
      hours: duration.h,
      guests: g,
      addons: lines.slice(1).map(function (l) { return l.id; }),
      lines: lines,
      total: total,
      low: Math.max(nice(total * prices.range.low), fmt.min),
      high: nice(total * prices.range.high),
      per_guest: round(total / g / 100) * 100
    };
  }

  function describe(est) {
    return est.format.title + ', уровень «' + est.level.title + '», ' + guestsNom(est.guests) + ', ' + hoursLabel(est.hours);
  }

  function rangeText(est) { return num(est.low) + ' – ' + money(est.high); }

  // ---- График работы агентства (по Москве) ----
  function zonedNow(date, tz) {
    var parts = {};
    try {
      new Intl.DateTimeFormat('en-GB', { timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
        .formatToParts(date)
        .forEach(function (p) { parts[p.type] = p.value; });
    } catch (e) { /* старый браузер без часовых поясов — берём местное время */ }
    var wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(parts.weekday);
    if (wd < 0) return { wd: date.getDay(), h: date.getHours(), m: date.getMinutes() };
    return { wd: wd, h: Number(parts.hour) % 24, m: Number(parts.minute) };
  }

  // Возвращает {open, closes, next, wd} — как work_status() в core/schedule.py
  function workStatus(date, schedule) {
    var t = zonedNow(date, schedule.tz);
    var hoursFor = function (wd) { return wd === 0 || wd === 6 ? schedule.weekend : schedule.weekday; };
    var hh = hoursFor(t.wd);
    var mins = t.h * 60 + t.m;
    if (mins >= hh[0] * 60 && mins < hh[1] * 60) return { open: true, closes: hh[1], next: '', wd: t.wd };
    if (mins < hh[0] * 60) return { open: false, closes: null, next: 'сегодня в ' + hh[0] + ':00', wd: t.wd };
    return { open: false, closes: null, next: 'завтра в ' + hoursFor((t.wd + 1) % 7)[0] + ':00', wd: t.wd };
  }

  var api = {
    plural: plural, num: num, money: money, guestsNom: guestsNom, guestsGen: guestsGen, hoursLabel: hoursLabel,
    shortRange: shortRange, addonHint: addonHint, normalize: normalize, estimate: estimate, describe: describe,
    rangeText: rangeText, workStatus: workStatus
  };

  if (typeof module === 'object' && module.exports) module.exports = api;  // для проверки в Node.js
  else root.SmetaEngine = api;  // для браузера
})(typeof self !== 'undefined' ? self : this);
