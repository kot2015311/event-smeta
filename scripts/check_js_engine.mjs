// Сверяет браузерный движок сметы (app/static/js/engine.js) с эталоном.
// Эталон — сметы из первого макета сайта: tests/golden_estimates.json.
// Запуск: node scripts/check_js_engine.mjs   (это же делает CI)
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const engine = require('../app/static/js/engine.js');
const prices = JSON.parse(readFileSync(new URL('../core/prices.json', import.meta.url), 'utf8'));
const golden = JSON.parse(readFileSync(new URL('../tests/golden_estimates.json', import.meta.url), 'utf8'));

let failed = 0;
for (const c of golden.cases) {
  const e = engine.estimate(c.input, prices);
  const got = {
    format: e.format.id, level: e.level.id, hours: e.hours, guests: e.guests,
    total: e.total, low: e.low, high: e.high, per_guest: e.per_guest,
    lines: e.lines.map((l) => ({ id: l.id, sum: l.sum, note: l.note })),
  };
  if (JSON.stringify(got) !== JSON.stringify(c.expected)) {
    failed += 1;
    if (failed <= 3) console.error('Расхождение:', c.name, '\n  получили', JSON.stringify(got), '\n  ожидали ', JSON.stringify(c.expected));
  }
}

// Подсказки на карточках услуг («от 800 ₽/гость») тоже должны совпасть
for (const rule of prices.addons) {
  const hint = engine.addonHint(rule).replace(/\u00A0/g, ' ');
  if (hint !== golden.hints[rule.id]) {
    failed += 1;
    console.error('Подсказка не совпала:', rule.id, hint, '≠', golden.hints[rule.id]);
  }
}

// Нормализация параметров: мусор на входе не должен ломать расчёт
const n = engine.normalize({ guests: 'abc', hours: 'x', addons: 'host,unknown,host', format: '' }, prices);
if (n.guests !== 50 || n.hours !== 4 || n.addons.join() !== 'host' || n.format !== 'corporate') {
  failed += 1;
  console.error('normalize() вернул неожиданное:', n);
}

if (failed) {
  console.error(`JS-движок разошёлся с эталоном. Ошибок: ${failed}, проверено смет: ${golden.cases.length}`);
  process.exit(1);
}
console.log(`JS-движок совпал с эталоном. Проверено смет: ${golden.cases.length}`);
