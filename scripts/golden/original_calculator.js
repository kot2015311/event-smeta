// Калькулятор из первого макета сайта (версия А, октябрь 2026) — эталон для тестов.
// Не используется сайтом: только для генерации tests/golden_estimates.json.
    const NB = '\u00A0';
    const plural = (n, a, b, c) => { n = Math.abs(n) % 100; const d = n % 10; return (n > 10 && n < 20) ? c : (d > 1 && d < 5) ? b : (d === 1) ? a : c; };
    const nf = new Intl.NumberFormat('ru-RU');
    const num = (n) => nf.format(Math.round(n)).replace(/[\u202F\u00A0 ]/g, NB);
    const money = (n) => num(n) + NB + '₽';
    const gNom = (n) => n + NB + plural(n, 'гость', 'гостя', 'гостей');
    const gGen = (n) => n + NB + plural(n, 'гостя', 'гостей', 'гостей');
    const r500 = (v) => Math.round(v / 500) * 500;
    const nice = (x) => { const st = x < 100000 ? 1000 : x < 500000 ? 5000 : x < 2000000 ? 10000 : 50000; return Math.round(x / st) * st; };
    const short = (lo, hi) => {
      if (hi < 1000000) return Math.round(lo / 1000) + '–' + Math.round(hi / 1000) + NB + 'тыс.' + NB + '₽';
      const f = (v) => (v / 1000000).toFixed(1).replace('.', ',');
      return f(lo) + '–' + f(hi) + NB + 'млн' + NB + '₽';
    };

    // Настройки: часовой пояс и график (пн–пт 8–17, сб–вс 10–15), вилка цены, границы числа гостей
    const CFG = { tz: 'Europe/Moscow', weekday: [8, 17], weekend: [10, 15], lo: 0.9, hi: 1.12, gMin: 10, gMax: 500 };

    const ICON = {"briefcase": "M4 7h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2ZM16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16", "wine": "M8 22h8M7 10h10M12 15v7M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z", "tent": "M3.5 21 14 3M20.5 21 10 3M15.5 21 12 15l-3.5 6M2 21h20", "megaphone": "m3 11 18-5v12L3 14v-3zM11.6 16.8a3 3 0 1 1-5.8-1.6", "trophy": "M6 9H4.5a2.5 2.5 0 0 1 0-5H6M18 9h1.5a2.5 2.5 0 0 0 0-5H18M4 22h16M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22M18 2H6v7a6 6 0 0 0 12 0V2Z", "mic": "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3ZM19 10v2a7 7 0 0 1-14 0v-2M12 19v3", "speaker": "M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2ZM12 6h.01M16 14a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 14h.01", "utensils": "M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7", "clipboard": "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1ZM16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 14l2 2 4-4", "users": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75", "camera": "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3zM12 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z", "gift": "M4 8h16a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1ZM12 8v13M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5", "palette": "M13.5 6.5h.01M17.5 10.5h.01M8.5 7.5h.01M6.5 12.5h.01M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z", "layout": "M4 3h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM4 14h7a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1ZM17 14h3a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1Z", "pin": "M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0ZM12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z", "bus": "M8 6v6M15 6v6M2 12h19.6M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3M7 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM9 18h5M16 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z", "sparkles": "m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3ZM5 3v4M19 17v4M3 5h4M17 19h4", "zap": "M13 2 3 14h9l-1 8 10-12h-9l1-8z", "phone": "M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z", "mail": "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM22 7l-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7", "send": "m22 2-7 20-4-9-9-4ZM22 2 11 13", "clock": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20ZM12 6v6l4 2", "check": "M20 6 9 17l-5-5", "arrow": "M5 12h14M12 5l7 7-7 7", "back": "M12 19l-7-7 7-7M19 12H5", "plus": "M5 12h14M12 5v14", "minus": "M5 12h14", "refresh": "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5"};

    // Базовая вилка «организация и сценарий» для 50 гостей и 4 часов (₽)
    const FORMATS = [
      { id: 'business', icon: 'briefcase', title: 'Деловое мероприятие', desc: 'Конференции, семинары, презентации, форумы', min: 30000, max: 80000 },
      { id: 'corporate', icon: 'wine', title: 'Корпоратив', desc: 'Праздники, новый год, день компании, тематические вечеринки', min: 150000, max: 500000 },
      { id: 'offsite', icon: 'tent', title: 'Выездное мероприятие', desc: 'Выезд за город, стратегические сессии, фестивали для команды', min: 140000, max: 300000 },
      { id: 'pr', icon: 'megaphone', title: 'PR и маркетинг', desc: 'Запуск продукта, пресс-события, промо-акции, спецпроекты', min: 120000, max: 250000 },
      { id: 'team', icon: 'trophy', title: 'Тимбилдинг', desc: 'Командные игры, квесты, спортивные программы', min: 60000, max: 180000 }
    ];

    // Уровень сдвигает цену внутри вилки и множитель услуг
    const LEVELS = [
      { id: 'standard', title: 'Стандарт', tag: 'Бюджетно', desc: 'Проверенные подрядчики, базовое оформление, чёткая программа', pos: 0, mult: 1 },
      { id: 'comfort', title: 'Комфорт', tag: 'Оптимально', desc: 'Расширенная программа, продуманный декор и техника', pos: 0.45, mult: 1.4 },
      { id: 'premium', title: 'Премиум', tag: 'Максимум', desc: 'Авторская концепция, топовые подрядчики, максимум внимания', pos: 1, mult: 2 }
    ];

    const HOURS = [
      { h: 2, label: '2 часа', k: 0.9 },
      { h: 4, label: '4 часа', k: 1 },
      { h: 6, label: '6 часов', k: 1.15 },
      { h: 8, label: '8 часов', k: 1.3 }
    ];

    // c = { g: гостей, h: часов, L: индекс уровня 0..2, m: множитель уровня }
    const ADDONS = [
      { id: 'venue', icon: 'pin', title: 'Площадка', hint: 'от 800 ₽/гость',
        calc: (c) => ({ sum: Math.max(40000, c.g * [800, 1400, 2600][c.L]), note: 'подбор и аренда' }) },
      { id: 'host', icon: 'mic', title: 'Ведущий', hint: 'от 3 000 ₽/час',
        calc: (c) => ({ sum: 3000 * c.h * c.m, note: c.h + ' ч работы' }) },
      { id: 'show', icon: 'sparkles', title: 'Шоу и артисты', hint: 'от 40 000 ₽',
        calc: (c) => ({ sum: [40000, 90000, 250000][c.L], note: ['диджей или музыкант', 'кавер-группа или шоу', 'артисты и спецэффекты'][c.L] }) },
      { id: 'workshop', icon: 'palette', title: 'Мастер-класс', hint: 'от 2 000 ₽/гость',
        calc: (c) => ({ sum: Math.max(30000, c.g * [2000, 2600, 3500][c.L]), note: 'на ' + gGen(c.g) }) },
      { id: 'av', icon: 'speaker', title: 'Свет и звук', hint: 'от 30 000 ₽',
        calc: (c) => ({ sum: (30000 + Math.max(0, c.g - 50) * 300) * c.m, note: 'комплект на ' + gGen(c.g) }) },
      { id: 'design', icon: 'layout', title: 'Оформление и фирменный стиль', hint: 'от 35 000 ₽',
        calc: (c) => ({ sum: [35000, 90000, 210000][c.L], note: ['графика и навигация', 'базовый фирменный стиль', 'расширенный стиль и декор'][c.L] }) },
      { id: 'catering', icon: 'utensils', title: 'Кейтеринг', hint: 'от 1 000 ₽/гость',
        calc: (c) => ({ sum: Math.max(50000, c.g * 1000 * c.m), note: 'на ' + gGen(c.g) }) },
      { id: 'gifts', icon: 'gift', title: 'Подарки с логотипом', hint: 'от 1 370 ₽/шт.',
        calc: (c) => { const d = c.g >= 300 ? 0.3 : c.g >= 150 ? 0.2 : c.g >= 50 ? 0.1 : 0; return { sum: c.g * [1370, 2200, 4900][c.L] * (1 - d), note: c.g + ' шт.' + (d ? ' · скидка ' + Math.round(d * 100) + '%' : '') }; } },
      { id: 'media', icon: 'camera', title: 'Фото и видео', hint: 'от 25 000 ₽',
        calc: (c) => ({ sum: [25000, 45000, 120000][c.L], note: ['репортаж и ролик', 'расширенная съёмка и фильм', 'премиальный продакшн'][c.L] }) },
      { id: 'transfer', icon: 'bus', title: 'Трансфер', hint: 'от 25 000 ₽/автобус',
        calc: (c) => { const n = Math.ceil(c.g / 50); return { sum: 25000 * n * c.m, note: n + ' ' + plural(n, 'автобус', 'автобуса', 'автобусов') + ', туда и обратно' }; } },
      { id: 'coord', icon: 'clipboard', title: 'Координатор', hint: 'от 4 000 ₽/день',
        calc: (c) => { const n = Math.ceil(c.g / 100); return { sum: 4000 * n * c.m, note: n + ' ' + plural(n, 'координатор', 'координатора', 'координаторов') + ' на день' }; } },
      { id: 'promo', icon: 'users', title: 'Промоперсонал', hint: 'от 500 ₽/час',
        calc: (c) => { const n = Math.max(2, Math.ceil(c.g / 40)); return { sum: 500 * c.h * n * c.m, note: n + ' ' + plural(n, 'человек', 'человека', 'человек') + ' × ' + c.h + ' ч' }; } }
    ];

    // Готовые сценарии для раздела с примерами
    const PRESETS = [
      { no: 'I', title: 'Конференция на 80 человек', state: { format: 'business', guests: 80, hours: 6, level: 'comfort', addons: ['host', 'av', 'catering', 'coord', 'media'] } },
      { no: 'II', title: 'Новогодний корпоратив на 80 человек', state: { format: 'corporate', guests: 80, hours: 4, level: 'standard', addons: ['host', 'show', 'av', 'catering', 'gifts'] } },
      { no: 'III', title: 'Выезд команды на 40 человек', state: { format: 'offsite', guests: 40, hours: 8, level: 'standard', addons: ['workshop', 'catering', 'transfer', 'coord', 'media'] } }
    ];

    const estimate = (s) => {
      const fmt = FORMATS.find((f) => f.id === s.format) || FORMATS[1];
      const li = Math.max(0, LEVELS.findIndex((l) => l.id === s.level));
      const lv = LEVELS[li];
      const du = HOURS.find((d) => d.h === s.hours) || HOURS[1];
      const g = Math.min(CFG.gMax, Math.max(CFG.gMin, Math.round(s.guests)));
      const gk = g <= 50 ? 1 : Math.pow(g / 50, 0.7);
      const base = Math.max(fmt.min, (fmt.min + (fmt.max - fmt.min) * lv.pos) * gk * du.k);
      const c = { g: g, h: du.h, L: li, m: lv.mult };
      const lines = [{ id: 'base', title: 'Организация и сценарий', note: fmt.title + ' · ' + lv.title, sum: r500(base) }];
      ADDONS.forEach((a) => {
        if ((s.addons || []).indexOf(a.id) > -1) { const r = a.calc(c); lines.push({ id: a.id, title: a.title, note: r.note, sum: r500(r.sum) }); }
      });
      const total = lines.reduce((t, l) => t + l.sum, 0);
      return { fmt: fmt, lv: lv, du: du, g: g, lines: lines, total: total, low: Math.max(nice(total * CFG.lo), fmt.min), high: nice(total * CFG.hi), per: Math.round(total / g / 100) * 100 };
    };

    // Рабочие часы считаем по поясу агентства
    const mskNow = (d) => {
      const p = {};
      try { new Intl.DateTimeFormat('en-GB', { timeZone: CFG.tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d).forEach((x) => { p[x.type] = x.value; }); } catch (e) { /* без пояса */ }
      const wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(p.weekday);
      return wd < 0 ? { wd: d.getDay(), h: d.getHours(), m: d.getMinutes() } : { wd: wd, h: (+p.hour) % 24, m: +p.minute };
    };
    const hoursFor = (wd) => (wd === 0 || wd === 6) ? CFG.weekend : CFG.weekday;
    const workStatus = (d) => {
      const t = mskNow(d), hh = hoursFor(t.wd), mins = t.h * 60 + t.m;
      if (mins >= hh[0] * 60 && mins < hh[1] * 60) return { open: true, closes: hh[1], wd: t.wd };
      if (mins < hh[0] * 60) return { open: false, next: 'сегодня в ' + hh[0] + ':00', wd: t.wd };
      return { open: false, next: 'завтра в ' + hoursFor((t.wd + 1) % 7)[0] + ':00', wd: t.wd };
    };

