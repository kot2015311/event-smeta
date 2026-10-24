// Генерирует эталонные сметы из калькулятора первого макета (версия А).
// Запуск: node scripts/golden/make_golden.mjs tests/golden_estimates.json
// Новый движок (Python и JS) обязан выдавать те же суммы.
import { readFileSync, writeFileSync } from 'node:fs';

const body = readFileSync(new URL('./original_calculator.js', import.meta.url), 'utf8');
const factory = new Function(body + '\nreturn { estimate, FORMATS, LEVELS, HOURS, ADDONS, PRESETS, CFG };');
const D = factory();

// Детерминированный генератор случайных чисел, чтобы файл был одинаковым при каждом запуске
let seed = 20261024;
const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const pick = (arr) => arr[Math.floor(rnd() * arr.length)];

const formats = D.FORMATS.map((f) => f.id);
const levels = D.LEVELS.map((l) => l.id);
const hours = D.HOURS.map((h) => h.h);
const addons = D.ADDONS.map((a) => a.id);
const guestsList = [10, 15, 23, 40, 49, 50, 51, 80, 99, 100, 101, 120, 137, 149, 150, 151, 200, 250, 299, 300, 301, 350, 420, 495, 500];

const cases = [];
// 1) Готовые примеры со страницы
D.PRESETS.forEach((p) => cases.push({ name: 'preset: ' + p.title, input: p.state }));
// 2) Все форматы × все уровни, по одному набору услуг
formats.forEach((f) => levels.forEach((l) => cases.push({ name: `grid ${f}/${l}`, input: { format: f, level: l, guests: 80, hours: 4, addons: addons.slice() } })));
// 3) Каждая услуга отдельно на разных масштабах (проверяем формулы и подписи)
addons.forEach((a) => [10, 50, 51, 150, 300, 500].forEach((g) => levels.forEach((l) => cases.push({ name: `addon ${a} g=${g} ${l}`, input: { format: 'business', level: l, guests: g, hours: pick(hours), addons: [a] } }))));
// 4) Случайные сочетания
for (let i = 0; i < 160; i++) {
  const chosen = addons.filter(() => rnd() < 0.45);
  cases.push({ name: 'random #' + (i + 1), input: { format: pick(formats), level: pick(levels), guests: pick(guestsList), hours: pick(hours), addons: chosen } });
}
// 5) Края: неизвестные значения и выход за границы
cases.push({ name: 'edge: мало гостей', input: { format: 'corporate', level: 'comfort', guests: 3, hours: 4, addons: ['host'] } });
cases.push({ name: 'edge: много гостей', input: { format: 'corporate', level: 'premium', guests: 9000, hours: 8, addons: addons.slice() } });
cases.push({ name: 'edge: дробные гости', input: { format: 'team', level: 'standard', guests: 80.5, hours: 2, addons: ['gifts', 'promo'] } });
cases.push({ name: 'edge: неизвестный формат', input: { format: 'wedding', level: 'comfort', guests: 50, hours: 4, addons: [] } });
cases.push({ name: 'edge: неизвестный уровень', input: { format: 'pr', level: 'vip', guests: 50, hours: 4, addons: ['show'] } });
cases.push({ name: 'edge: неизвестная длительность', input: { format: 'offsite', level: 'comfort', guests: 120, hours: 5, addons: ['transfer', 'coord'] } });
cases.push({ name: 'edge: неизвестная услуга', input: { format: 'business', level: 'standard', guests: 30, hours: 2, addons: ['fireworks', 'media'] } });

const out = cases.map((c) => {
  const e = D.estimate(c.input);
  return {
    name: c.name,
    input: c.input,
    expected: {
      format: e.fmt.id, level: e.lv.id, hours: e.du.h, guests: e.g,
      total: e.total, low: e.low, high: e.high, per_guest: e.per,
      lines: e.lines.map((l) => ({ id: l.id, sum: l.sum, note: l.note })),
    },
  };
});

const hints = Object.fromEntries(D.ADDONS.map((a) => [a.id, a.hint.replace(/\u00A0/g, ' ')]));
writeFileSync(process.argv[2], JSON.stringify({
  source: 'Калькулятор из первого макета сайта (версия А, 12.10.2026). Сгенерировано: node scripts/golden/make_golden.mjs tests/golden_estimates.json',
  hints,
  cases: out,
}, null, 1) + '\n');
console.log(`Готово. Смет в эталоне: ${out.length}`);
