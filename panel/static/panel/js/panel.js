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
     16. Password visibility toggle
     17. Submit-once guard
     18. The counter — tally, steppers, scanner
     19. Events — stock picker, line totals
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
      var mark = function () { dirty = true; form.classList.add('is-dirty'); };
      form.addEventListener('input', mark);
      form.addEventListener('change', mark);
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

  /* ----------------------------------------- 16. password visibility toggle */

  (function passwordToggle() {
    $$('[data-password-toggle]').forEach(function (button) {
      var input = $('.field__input', button.parentNode);
      if (!input) { return; }

      button.addEventListener('click', function () {
        var showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        button.setAttribute('aria-pressed', String(!showing));
        button.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
        $('use', button).setAttribute('href', showing ? '#p-eye' : '#p-eye-off');
      });
    });
  }());

  /* ------------------------------------------------------- 17. submit once */

  (function submitOnce() {
    // Two taps on "Complete sale" must not be two sales. The server refuses the
    // second one anyway; this stops it being sent and makes the wait visible.
    $$('[data-once]').forEach(function (form) {
      form.addEventListener('submit', function () {
        // After the tick, so the browser has already collected the submitter's
        // name and value — disabling it any sooner drops the button's value.
        setTimeout(function () {
          $$('button[type="submit"], input[type="submit"]', form).forEach(function (button) {
            button.disabled = true;
          });
          form.classList.add('is-sending');
        }, 0);
      });
    });

    window.addEventListener('pageshow', function (event) {
      if (!event.persisted) { return; }
      // Restored from the back/forward cache, so its statuses and counts may
      // be out of date: fetch it again rather than show the old copy.
      if (!document.querySelector('[data-dirty-guard].is-dirty')) {
        window.location.reload();
        return;
      }
      // A half-filled form is worth more than fresh numbers: let it be used again.
      $$('[data-once]').forEach(function (form) {
        form.classList.remove('is-sending');
        $$('button[type="submit"], input[type="submit"]', form).forEach(function (button) {
          button.disabled = false;
        });
      });
    });
  }());

  /* -------------------------------------------------------------- 18. till */

  (function till() {
    var root = $('[data-till]');
    if (!root) { return; }

    /* -- the running tally --------------------------------------------- */

    var close = $('.till__close', root);
    var anchor = close && $('[data-subtotal]', close);
    var discount = close && $('#id_discount', close);
    var tax = close && $('#id_tax_percent', close);
    var tendered = close && $('#id_amount_tendered', close);
    var discountOut = close && $('[data-discount-out]', close);
    var taxOut = close && $('[data-tax-out]', close);
    var changeOut = close && $('[data-change-out]', close);
    var changeRow = close && $('[data-change-row]', close);

    if (anchor && discount && tax && tendered && discountOut && taxOut && changeOut && changeRow) {
      var subtotal = parseInt(anchor.dataset.subtotal, 10) || 0;
      var totals = $$('[data-total-out]', root);

      var rupees = function (value) {
        return '₹' + Math.round(value).toLocaleString('en-IN');
      };

      var recalc = function () {
        var off = Math.min(Math.max(parseFloat(discount.value) || 0, 0), subtotal);
        var net = subtotal - off;
        var taxed = Math.round(net * (parseFloat(tax.value) || 0) / 100);
        var total = net + taxed;
        var paid = parseFloat(tendered.value) || 0;
        var owing = paid > total;

        discountOut.textContent = off ? '−' + rupees(off) : '₹0';
        taxOut.textContent = rupees(taxed);
        totals.forEach(function (cell) { cell.textContent = rupees(total); });

        changeRow.hidden = !owing;
        changeOut.hidden = !owing;
        if (owing) { changeOut.textContent = rupees(paid - total); }

        // Over the subtotal is a typo, not a discount.
        discount.classList.toggle('is-invalid', (parseFloat(discount.value) || 0) > subtotal);
      };

      [discount, tax, tendered].forEach(function (input) {
        input.addEventListener('input', recalc);
      });
      recalc();
    }

    /* -- quantity steppers and price overrides -------------------------- */

    // Each basket line is its own form, so applying a change means submitting
    // that form through its own hidden button — which carries the action the
    // view reads. Each line gets its own timer: a shared one would let a change
    // to the second line swallow an unsent change to the first.
    var busy = false;

    function applier(form) {
      return debounce(function () {
        if (busy) { return; }
        busy = true;
        form.classList.add('is-sending');
        root.classList.add('is-busy');
        var button = $('.basket__apply', form);
        if (button) { button.click(); } else { form.submit(); }
      }, 420);
    }

    $$('[data-line]', root).forEach(function (form) {
      var quantity = $('[data-qty]', form);
      var price = $('[data-price]', form);
      var apply = applier(form);
      if (!quantity) { return; }

      $$('[data-step]', form).forEach(function (button) {
        button.addEventListener('click', function () {
          var by = parseFloat(button.dataset.step) || 0;
          var next = Math.max((parseFloat(quantity.value) || 0) + by, 0);
          // Tapping + four times should send one request, not four.
          quantity.value = String(Math.round(next * 100) / 100);
          apply();
        });
      });

      [quantity, price].forEach(function (input) {
        if (!input) { return; }
        input.addEventListener('change', function () { apply(); });
        input.addEventListener('keydown', function (event) {
          if (event.key === 'Enter') { event.preventDefault(); apply(); }
        });
      });
    });

    /* -- the scanner ---------------------------------------------------- */

    var scan = $('[data-scan]', root);
    if (scan) {
      // A till is driven by a scanner, so the code box owns the keyboard —
      // but not on a phone, where focusing it throws up the keyboard on load.
      if (window.matchMedia('(min-width: 900px)').matches) { scan.focus(); }

      document.addEventListener('keydown', function (event) {
        if (event.key !== '/' || event.defaultPrevented) { return; }
        var inField = event.target.closest('input, textarea, select, [contenteditable]');
        if (inField) { return; }
        event.preventDefault();
        scan.focus();
        scan.select();
      });

      scan.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { scan.value = ''; scan.blur(); }
      });
    }
  }());

  /* ------------------------------------------------------------ 19. events */

  // The stock picker on an event: tick any number of items, each with its own
  // quantity, and see straight away when one asks for more than is free. The
  // server checks everything again under a lock — this only saves a round trip.
  // Without JavaScript the ticks and quantity boxes still post as they are.
  (function stockPicker() {
    $$('[data-stock-picker]').forEach(function (form) {
      var picks = $$('[data-pick]', form);
      if (!picks.length) { return; }
      var bar = $('[data-pick-bar]', form);
      var filter = $('[data-pick-filter]', form);
      var kinds = $$('[data-pick-kind]', form);
      var count = $('[data-pick-count]', form);
      var empty = $('[data-pick-empty]', form);
      var summary = $('[data-pick-summary]', form);
      var submit = $('[data-pick-submit]', form);
      var label = $('[data-pick-label]', form);
      var kind = '';

      if (bar) { bar.hidden = false; }

      function parts(pick) {
        return {
          check: $('.pick__check', pick),
          qty: $('.pick__qty input', pick),
          err: $('[data-pick-err]', pick),
          steps: $$('[data-pick-step]', pick)
        };
      }

      // What is wrong with this tile's quantity, or '' when it is fine.
      function problem(pick) {
        var p = parts(pick);
        if (!p.check.checked) { return ''; }
        var raw = p.qty.value.trim();
        var wanted = Number(raw);
        if (!raw || !isFinite(wanted)) { return 'Enter a number.'; }
        if (wanted <= 0) { return 'The quantity has to be more than zero.'; }
        if (pick.hasAttribute('data-whole') && Math.floor(wanted) !== wanted) {
          return 'Reusable stock is counted in whole units.';
        }
        // A line already on the event that holds nothing yet needs its share too.
        var extra = parseFloat(pick.dataset.extra) || 0;
        var free = parseFloat(pick.dataset.available) || 0;
        if (wanted + extra > free) { return 'Only ' + pick.dataset.available + ' units are available.'; }
        return '';
      }

      function paint(pick) {
        var p = parts(pick);
        var on = p.check.checked;
        // Until the tile is touched, the server's word on it stands.
        var message = pick.dataset.touched ? problem(pick) : (p.err.textContent.trim() || problem(pick));
        pick.classList.toggle('is-picked', on);
        pick.classList.toggle('is-error', !!message);
        p.err.textContent = message;
        p.err.hidden = !message;
        p.steps.forEach(function (step) { step.hidden = false; step.disabled = p.qty.disabled; });
        return { on: on, bad: !!message };
      }

      function refresh() {
        var ticked = 0;
        var bad = 0;
        picks.forEach(function (pick) {
          var state = paint(pick);
          if (state.on) { ticked += 1; }
          if (state.bad) { bad += 1; }
        });
        if (count) { count.textContent = ticked; }
        if (label) {
          label.textContent = ticked === 0 ? 'Add ticked items'
            : 'Add ' + ticked + ' item' + (ticked === 1 ? '' : 's') + ' to the event';
        }
        if (submit) { submit.disabled = ticked === 0; }
        if (summary) {
          summary.classList.toggle('is-warn', bad > 0);
          if (bad) {
            summary.textContent = bad + ' ticked item' + (bad === 1 ? ' asks' : 's ask') + ' for more than it can have.';
          } else if (ticked) {
            summary.textContent = ticked + ' item' + (ticked === 1 ? '' : 's') + ' ticked.';
          } else {
            summary.textContent = 'Tick the items this event needs and set how many of each.';
          }
        }
        applyFilter();
      }

      function applyFilter() {
        var term = filter ? filter.value.trim().toLowerCase() : '';
        var shown = 0;
        picks.forEach(function (pick) {
          var check = $('.pick__check', pick);
          var hit = (!term || (pick.dataset.search || '').indexOf(term) !== -1) &&
            (!kind || (kind === 'picked' ? check.checked : pick.dataset.kind === kind));
          pick.hidden = !hit;
          if (hit) { shown += 1; }
        });
        if (empty) {
          empty.hidden = shown > 0;
          empty.textContent = kind === 'picked' && !term ? 'Nothing is ticked yet.' : 'No stock item matches that.';
        }
      }

      picks.forEach(function (pick) {
        var p = parts(pick);
        var touch = function () { pick.dataset.touched = '1'; };
        p.check.addEventListener('change', touch);
        p.qty.addEventListener('input', touch);
        p.steps.forEach(function (step) { step.addEventListener('click', touch); });
        p.check.addEventListener('change', function () {
          if (p.check.checked && (!p.qty.value.trim() || Number(p.qty.value) <= 0)) { p.qty.value = '1'; }
          refresh();
        });
        p.qty.addEventListener('input', function () {
          // Typing a quantity is as good as ticking the box.
          if (!p.check.checked && !p.check.disabled && p.qty.value.trim()) { p.check.checked = true; }
          refresh();
        });
        p.qty.addEventListener('focus', function () { p.qty.select(); });
        p.steps.forEach(function (step) {
          step.addEventListener('click', function () {
            if (p.qty.disabled) { return; }
            var next = Math.floor((Number(p.qty.value) || 0) + Number(step.dataset.pickStep));
            if (next < 1) {
              p.check.checked = false;
              p.qty.value = '1';
            } else {
              p.qty.value = String(next);
              if (!p.check.disabled) { p.check.checked = true; }
            }
            refresh();
          });
        });
      });

      kinds.forEach(function (button) {
        button.addEventListener('click', function () {
          kind = button.dataset.pickKind;
          kinds.forEach(function (other) {
            var on = other === button;
            other.classList.toggle('is-on', on);
            other.setAttribute('aria-pressed', on ? 'true' : 'false');
          });
          applyFilter();
        });
      });

      if (filter) {
        filter.addEventListener('input', applyFilter);
        filter.addEventListener('keydown', function (event) {
          if (event.key !== 'Enter') { return; }
          // Enter picks the only match rather than sending the form.
          event.preventDefault();
          var visible = picks.filter(function (pick) { return !pick.hidden; });
          if (visible.length !== 1) { return; }
          var p = parts(visible[0]);
          if (p.check.disabled) { return; }
          p.check.checked = true;
          refresh();
          p.qty.focus();
        });
      }

      // A quantity box sends the form on Enter; do that only once a tick exists.
      form.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && event.target.matches('.pick__qty input') && submit && submit.disabled) {
          event.preventDefault();
        }
      });

      refresh();
    });
  }());

  // Quantity × unit cost, for an external item, as it is typed.
  (function lineTotals() {
    $$('[data-line-total]').forEach(function (form) {
      var quantity = $('input[name="quantity"]', form);
      var cost = $('input[name="unit_cost"]', form);
      var out = $('[data-line-total-out]', form);
      if (!quantity || !cost || !out) { return; }

      function recalc() {
        var total = (parseFloat(quantity.value) || 0) * (parseFloat(cost.value) || 0);
        out.textContent = '₹' + Math.round(total).toLocaleString('en-IN');
      }
      quantity.addEventListener('input', recalc);
      cost.addEventListener('input', recalc);
      recalc();
    });
  }());

  // An event page that comes back with a form error opens on that form.
  (function openDrawer() {
    var open = $('details.drawer[open]');
    if (!open || window.location.hash) { return; }
    open.scrollIntoView({ block: 'center', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
  }());
}());
