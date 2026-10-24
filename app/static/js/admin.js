/* Мелкие удобства CRM: копирование телефона, автоотправка фильтра, подтверждение без диалоговых окон */
(function () {
  'use strict';

  // Кнопка «скопировать»: data-copy="текст"
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      var done = function () {
        btn.classList.add('is-done');
        btn.setAttribute('aria-label', 'Скопировано');
        setTimeout(function () { btn.classList.remove('is-done'); btn.setAttribute('aria-label', 'Скопировать телефон'); }, 1500);
      };
      // Запасной способ для старых браузеров: временное поле и команда «копировать»
      var fallback = function () {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        try { if (document.execCommand('copy')) done(); } catch (err) { /* не получилось — номер виден рядом */ }
        document.body.removeChild(area);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
      else fallback();
    });
  });

  // Фильтр по формату применяется сразу, без кнопки «Найти»
  document.querySelectorAll('[data-autosubmit]').forEach(function (select) {
    select.addEventListener('change', function () { if (select.form) select.form.submit(); });
  });

  // Опасные кнопки срабатывают со второго нажатия: первое меняет надпись
  document.querySelectorAll('[data-confirm]').forEach(function (btn) {
    var armed = false;
    var label = btn.querySelector('span');
    var original = label ? label.textContent : '';
    btn.addEventListener('click', function (e) {
      if (armed) return;
      e.preventDefault();
      armed = true;
      if (label) label.textContent = btn.getAttribute('data-confirm');
      btn.classList.add('is-armed');
      setTimeout(function () {
        armed = false;
        if (label) label.textContent = original;
        btn.classList.remove('is-armed');
      }, 4000);
    });
  });
})();
