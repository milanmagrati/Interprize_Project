/* ==========================================================================
   Celebra control panel — panel.js
   No dependencies. Each block returns early if its markup is absent, so the
   panel degrades to plain forms and links with JavaScript off.

   Contents
     1.  Helpers
     2.  Sidebar drawer and scroll position
     3.  User menu
     4.  Toasts
     5.  Command palette
     6.  Inline switches
     7.  Bulk selection
     8.  Drag to reorder
     9.  Auto-submitting filters
     10. Confirmations
     11. Unsaved-changes guard
     12. Slug from title
     13. File input previews
     14. Copy to clipboard
     15. Theme switch
   ========================================================================== */

(function () {
  'use strict';

  /* ---------------------------------------------------------------- 1. helpers */

  function $(selector, scope) { return (scope || document).querySelector(selector); }
  function $$(selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  }

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    if (match) { return decodeURIComponent(match[1]); }
    var input = $('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function post(url, data) {
    var body = new FormData();
    Object.keys(data || {}).forEach(function (key) { body.append(key, data[key]); });
    return fetch(url, {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      if (!response.ok) { throw new Error('Request failed: ' + response.status); }
      return response.json();
    });
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  }

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ----------------------------------------------------------- 2. sidebar drawer */

  (function drawer() {
    var nav = $('[data-nav]');
    var scrim = $('[data-nav-scrim]');
    if (!nav || !scrim) { return; }

    var lastFocus = null;

    function open() {
      lastFocus = document.activeElement;
      nav.classList.add('is-open');
      scrim.hidden = false;
      document.body.style.overflow = 'hidden';
      var first = $('a, button', nav);
      if (first) { first.focus(); }
    }

    function close() {
      nav.classList.remove('is-open');
      scrim.hidden = true;
      document.body.style.overflow = '';
      if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
    }

    $$('[data-nav-open]').forEach(function (button) { button.addEventListener('click', open); });
    $$('[data-nav-close]').forEach(function (button) { button.addEventListener('click', close); });
    scrim.addEventListener('click', close);

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && nav.classList.contains('is-open')) { close(); }
    });

    // A wide viewport shows the sidebar permanently; drop the drawer state so
    // the body scroll lock never survives a rotation.
    window.matchMedia('(min-width: 1024px)').addEventListener('change', function (event) {
      if (event.matches) { close(); }
    });
  }());

  // A full page load rebuilds the sidebar, so its scroll box would start at the
  // top again and a section below the fold — Homepage, System — would jump away
  // the moment you click into it. base.html restores the saved offset inline,
  // before the first paint; this block keeps that offset up to date and handles
  // the case where there is nothing to restore.
  (function navPosition() {
    var nav = $('.side__nav');
    if (!nav) { return; }

    var KEY = 'celebra.panel.nav-scroll';

    function store() {
      try { sessionStorage.setItem(KEY, String(nav.scrollTop)); } catch (error) { /* storage off */ }
    }

    // First visit of the session, or a jump from somewhere other than the
    // sidebar: nothing was restored, so put the page you landed on on screen.
    if (!nav.dataset.restored) {
      var active = $('.nav__link.is-active', nav);
      if (active) {
        var box = nav.getBoundingClientRect();
        var link = active.getBoundingClientRect();
        if (link.top < box.top || link.bottom > box.bottom) {
          nav.scrollTop += link.top - box.top - (nav.clientHeight - link.height) / 2;
        }
      }
    }

    // Written on the click itself, not just on unload: pagehide is skipped often
    // enough (bfcache, a tab torn out) that a debounced scroll alone loses the
    // last few pixels of movement before the navigation.
    nav.addEventListener('pointerdown', store, true);
    nav.addEventListener('click', store, true);
    nav.addEventListener('scroll', debounce(store, 120), { passive: true });
    window.addEventListener('pagehide', store);
  }());

  /* ---------------------------------------------------------------- 3. user menu */

  (function userMenu() {
    var menu = $('[data-menu]');
    if (!menu) { return; }
    var button = $('[data-menu-btn]', menu);
    var pop = $('[data-menu-pop]', menu);
    if (!button || !pop) { return; }

    function setOpen(open) {
      pop.hidden = !open;
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    button.addEventListener('click', function () { setOpen(pop.hidden); });

    document.addEventListener('click', function (event) {
      if (!menu.contains(event.target)) { setOpen(false); }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { setOpen(false); }
    });
  }());

  /* ------------------------------------------------------------------ 4. toasts */

  (function toasts() {
    var items = $$('[data-toast]');
    if (!items.length) { return; }

    items.forEach(function (toast, index) {
      var close = $('[data-toast-close]', toast);
      function dismiss() {
        toast.classList.add('is-going');
        setTimeout(function () { toast.remove(); }, reducedMotion.matches ? 0 : 220);
      }
      if (close) { close.addEventListener('click', dismiss); }
      // Errors stay put — they usually need reading twice.
      if (toast.className.indexOf('toast--error') === -1) {
        setTimeout(dismiss, 4800 + index * 500);
      }
    });
  }());

  /* -------------------------------------------------------- 5. command palette */

  (function palette() {
    var root = $('[data-palette]');
    if (!root) { return; }

    var input = $('[data-palette-input]', root);
    var results = $('[data-palette-results]', root);
    var endpoint = '/manage/search/';
    var cursor = -1;
    var lastFocus = null;

    function open() {
      lastFocus = document.activeElement;
      root.hidden = false;
      document.body.style.overflow = 'hidden';
      input.value = '';
      input.focus();
      load('');
    }

    function close() {
      root.hidden = true;
      document.body.style.overflow = '';
      cursor = -1;
      if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
    }

    function render(rows) {
      if (!rows.length) {
        results.innerHTML = '<p class="palette__hint">Nothing matches that.</p>';
        return;
      }
      var html = '';
      var group = '';
      rows.forEach(function (row, index) {
        if (row.group !== group) {
          group = row.group;
          html += '<p class="palette__group">' + escapeHtml(group) + '</p>';
        }
        html += '<a class="palette__hit" data-hit="' + index + '" href="' + escapeHtml(row.url) + '">' +
                '<strong>' + escapeHtml(row.label) + '</strong>' +
                '<span>' + escapeHtml(row.meta || '') + '</span></a>';
      });
      results.innerHTML = html;
      cursor = -1;
    }

    function escapeHtml(value) {
      return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    var load = debounce(function (term) {
      fetch(endpoint + '?q=' + encodeURIComponent(term), { credentials: 'same-origin' })
        .then(function (response) { return response.json(); })
        .then(function (data) { render(data.results || []); })
        .catch(function () {
          results.innerHTML = '<p class="palette__hint">Search is unavailable right now.</p>';
        });
    }, 160);

    function move(step) {
      var hits = $$('[data-hit]', results);
      if (!hits.length) { return; }
      cursor = (cursor + step + hits.length) % hits.length;
      hits.forEach(function (hit, index) { hit.classList.toggle('is-on', index === cursor); });
      hits[cursor].scrollIntoView({ block: 'nearest' });
    }

    $$('[data-palette-open]').forEach(function (button) { button.addEventListener('click', open); });
    $$('[data-palette-close]').forEach(function (button) { button.addEventListener('click', close); });

    input.addEventListener('input', function () { load(input.value.trim()); });

    input.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
      else if (event.key === 'Enter') {
        var hits = $$('[data-hit]', results);
        if (cursor >= 0 && hits[cursor]) { event.preventDefault(); hits[cursor].click(); }
      }
    });

    document.addEventListener('keydown', function (event) {
      var isShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
      if (isShortcut) { event.preventDefault(); root.hidden ? open() : close(); return; }
      if (event.key === 'Escape' && !root.hidden) { close(); }
      // "/" focuses search, unless the reader is already typing somewhere.
      if (event.key === '/' && root.hidden) {
        var tag = (document.activeElement.tagName || '').toLowerCase();
        if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
          event.preventDefault();
          open();
        }
      }
    });
  }());

  /* --------------------------------------------------------- 6. inline switches */

  (function switches() {
    var toggles = $$('[data-toggle]');
    if (!toggles.length) { return; }

    toggles.forEach(function (button) {
      button.addEventListener('click', function () {
        if (button.classList.contains('is-busy')) { return; }
        button.classList.add('is-busy');

        post(button.getAttribute('data-toggle'), {})
          .then(function (data) {
            button.classList.toggle('is-on', !!data.value);
            button.setAttribute('aria-checked', data.value ? 'true' : 'false');
          })
          .catch(function () {
            // The optimistic path failed; a reload is the honest fallback since
            // the row may now disagree with the database.
            window.location.reload();
          })
          .finally(function () { button.classList.remove('is-busy'); });
      });
    });
  }());

  /* ------------------------------------------------------------ 7. bulk actions */

  (function bulk() {
    var form = $('[data-bulk]');
    if (!form) { return; }

    var bar = $('[data-bulk-bar]', form);
    var count = $('[data-bulk-count]', form);
    var all = $('[data-bulk-all]', form);
    var boxes = $$('[data-bulk-one]', form);
    if (!bar || !boxes.length) { return; }

    function sync() {
      var checked = boxes.filter(function (box) { return box.checked; });
      count.textContent = checked.length;
      bar.hidden = checked.length === 0;
      if (all) {
        all.checked = checked.length === boxes.length;
        all.indeterminate = checked.length > 0 && checked.length < boxes.length;
      }
      boxes.forEach(function (box) {
        var row = box.closest('tr');
        if (row) { row.classList.toggle('is-checked', box.checked); }
      });
    }

    boxes.forEach(function (box) { box.addEventListener('change', sync); });

    if (all) {
      all.addEventListener('change', function () {
        boxes.forEach(function (box) { box.checked = all.checked; });
        sync();
      });
    }

    var clear = $('[data-bulk-clear]', form);
    if (clear) {
      clear.addEventListener('click', function () {
        boxes.forEach(function (box) { box.checked = false; });
        if (all) { all.checked = false; }
        sync();
      });
    }

    // Shift-click selects a range, the way every file manager does.
    var lastIndex = null;
    boxes.forEach(function (box, index) {
      box.addEventListener('click', function (event) {
        if (event.shiftKey && lastIndex !== null) {
          var from = Math.min(lastIndex, index);
          var to = Math.max(lastIndex, index);
          for (var i = from; i <= to; i += 1) { boxes[i].checked = box.checked; }
          sync();
        }
        lastIndex = index;
      });
    });

    sync();
  }());

  /* --------------------------------------------------------- 8. drag to reorder */

  (function reorder() {
    var table = $('[data-sortable]');
    if (!table) { return; }
    var body = $('[data-sortable-body]', table);
    if (!body) { return; }

    var endpoint = table.getAttribute('data-sortable');
    var dragged = null;

    $$('tr', body).forEach(function (row) {
      var handle = $('[data-drag-handle]', row);
      if (!handle) { return; }

      // Only the handle starts a drag, so text stays selectable in the row.
      handle.addEventListener('mousedown', function () { row.draggable = true; });
      handle.addEventListener('mouseup', function () { row.draggable = false; });

      row.addEventListener('dragstart', function (event) {
        dragged = row;
        row.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        // Firefox refuses to start a drag without data on the transfer.
        event.dataTransfer.setData('text/plain', row.getAttribute('data-id'));
      });

      row.addEventListener('dragend', function () {
        row.classList.remove('is-dragging');
        row.draggable = false;
        $$('tr', body).forEach(function (other) { other.classList.remove('is-over'); });
        save();
      });

      row.addEventListener('dragover', function (event) {
        if (!dragged || dragged === row) { return; }
        event.preventDefault();
        row.classList.add('is-over');
        var box = row.getBoundingClientRect();
        var below = event.clientY > box.top + box.height / 2;
        body.insertBefore(dragged, below ? row.nextSibling : row);
      });

      row.addEventListener('dragleave', function () { row.classList.remove('is-over'); });
    });

    function save() {
      var order = $$('tr', body).map(function (row) { return row.getAttribute('data-id'); });
      post(endpoint, { order: order.join(',') }).catch(function () {
        window.location.reload();
      });
    }
  }());

  /* ------------------------------------------------------- 9. filter auto-submit */

  (function autoSubmit() {
    $$('[data-autosubmit]').forEach(function (form) {
      $$('[data-submit]', form).forEach(function (control) {
        control.addEventListener('change', function () { form.submit(); });
      });
    });
  }());

  /* -------------------------------------------------------- 10. confirmations */

  (function confirmations() {
    document.addEventListener('click', function (event) {
      var trigger = event.target.closest('[data-confirm]');
      if (!trigger) { return; }
      if (!window.confirm(trigger.getAttribute('data-confirm'))) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  }());

  /* ---------------------------------------------------- 11. unsaved changes */

  (function dirtyGuard() {
    var forms = $$('[data-dirty-guard]');
    if (!forms.length) { return; }

    var dirty = false;
    var submitting = false;

    forms.forEach(function (form) {
      form.addEventListener('input', function () { dirty = true; });
      form.addEventListener('change', function () { dirty = true; });
      form.addEventListener('submit', function () { submitting = true; });
    });

    window.addEventListener('beforeunload', function (event) {
      if (!dirty || submitting) { return; }
      event.preventDefault();
      event.returnValue = '';
    });
  }());

  /* ------------------------------------------------------- 12. slug from title */

  (function slugify() {
    var slug = $('[data-field="slug"] input');
    if (!slug || slug.value) { return; }

    var source = $('[data-field="title"] input') || $('[data-field="name"] input');
    if (!source) { return; }

    var touched = false;
    slug.addEventListener('input', function () { touched = true; });

    source.addEventListener('input', function () {
      if (touched) { return; }
      slug.value = source.value
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .trim()
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .slice(0, 60);
    });
  }());

  /* ------------------------------------------------------ 13. upload previews */

  (function previews() {
    $$('input[type="file"]').forEach(function (input) {
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        if (!file || file.type.indexOf('image/') !== 0) { return; }

        var field = input.closest('.field');
        if (!field) { return; }

        var strip = $('.field__current', field);
        if (!strip) {
          strip = document.createElement('div');
          strip.className = 'field__current';
          strip.innerHTML = '<img alt="" width="60" height="45"><span></span>';
          input.parentNode.insertBefore(strip, input);
        }
        var image = $('img', strip);
        if (image) {
          if (image.dataset.blob) { URL.revokeObjectURL(image.dataset.blob); }
          var url = URL.createObjectURL(file);
          image.dataset.blob = url;
          image.src = url;
        }
        var label = $('span', strip);
        if (label) { label.textContent = 'New upload: ' + file.name; }
      });
    });
  }());

  /* ---------------------------------------------------- 14. copy to clipboard */

  (function copy() {
    $$('[data-copy]').forEach(function (element) {
      element.addEventListener('click', function () {
        var value = element.getAttribute('data-copy');
        var original = element.textContent;
        var done = function () {
          element.textContent = 'Copied';
          setTimeout(function () { element.textContent = original; }, 1200);
        };
        if (navigator.clipboard) {
          navigator.clipboard.writeText(value).then(done, function () {});
        }
      });
    });
  }());

  /* ------------------------------------------------------------ 15. theme swap */

  (function theme() {
    var form = $('[data-theme-form]');
    if (!form) { return; }

    form.addEventListener('submit', function () {
      // Paint the new theme before the round trip, so the switch feels instant.
      var next = $('input[name="theme"]', form);
      if (next) { document.documentElement.setAttribute('data-theme', next.value); }
    });
  }());
}());
