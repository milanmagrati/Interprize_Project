/* ==========================================================================
   Celebra — main.js
   Vanilla ES6, no dependencies. Every block bails out early if its markup
   is not on the page, so this one file serves every template.

   Contents
     1.  Helpers
     2.  Sticky header shade
     3.  Mobile drawer
     4.  City picker + city filtering
     5.  FAQ accordion (one open per group, animated height)
     6.  Testimonial carousel
     7.  Horizontal scroller arrows
     8.  Scroll reveal
     9.  Package gallery + lightbox
     10. Sticky mobile booking bar
     11. Listing filters drawer, range output, auto-submit sort
     12. Cart steppers and removal
     13. Add-to-cart toast
   ========================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------- 1. */
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  var rupees = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  // Escaped rather than a literal glyph, so the file survives re-encoding.
  var RUPEE = String.fromCharCode(0x20b9);
  function money(value) { return RUPEE + rupees.format(Math.round(value)); }

  function debounce(fn, wait) {
    var timer;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait || 150);
    };
  }

  var scrollLocks = 0;
  function lockScroll(on) {
    scrollLocks = Math.max(0, scrollLocks + (on ? 1 : -1));
    document.body.classList.toggle("is-locked", scrollLocks > 0);
  }

  /* ---------------------------------------------------------------- 2. */
  (function stickyHeader() {
    var header = $("[data-header]");
    if (!header) return;

    var onScroll = function () {
      header.classList.toggle("is-stuck", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  })();

  /* ---------------------------------------------------------------- 3. */
  (function mobileDrawer() {
    var toggle = $("[data-menu-toggle]");
    var panel = $("[data-menu-panel]");
    var scrim = $("[data-menu-scrim]");
    if (!toggle || !panel || !scrim) return;

    var closers = $$("[data-menu-close]");

    function open() {
      panel.hidden = false;
      scrim.hidden = false;
      // Next frame, so the transition has a starting state to move from.
      requestAnimationFrame(function () {
        panel.classList.add("is-open");
        scrim.classList.add("is-open");
      });
      toggle.setAttribute("aria-expanded", "true");
      lockScroll(true);
      var firstLink = $("a, button", panel);
      if (firstLink) firstLink.focus({ preventScroll: true });
    }

    function close() {
      if (toggle.getAttribute("aria-expanded") !== "true") return;
      panel.classList.remove("is-open");
      scrim.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      lockScroll(false);
      window.setTimeout(function () {
        if (!panel.classList.contains("is-open")) {
          panel.hidden = true;
          scrim.hidden = true;
        }
      }, 420);
      toggle.focus({ preventScroll: true });
    }

    toggle.addEventListener("click", function () {
      if (toggle.getAttribute("aria-expanded") === "true") close(); else open();
    });
    scrim.addEventListener("click", close);
    closers.forEach(function (btn) { btn.addEventListener("click", close); });
    $$("a", panel).forEach(function (link) { link.addEventListener("click", close); });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") close();
    });
  })();

  /* ---------------------------------------------------------------- 4. */
  (function cityPicker() {
    var picker = $("[data-city-picker]");
    if (picker) {
      document.addEventListener("click", function (event) {
        if (picker.open && !picker.contains(event.target)) picker.open = false;
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && picker.open) {
          picker.open = false;
          $("summary", picker).focus({ preventScroll: true });
        }
      });
    }

    // One filter box can drive any list tagged with a matching key.
    $$("[data-city-filter]").forEach(function (input) {
      var key = input.getAttribute("data-city-filter");
      var list = $('[data-city-list="' + key + '"]');
      var empty = $('[data-city-empty="' + key + '"]');
      if (!list) return;

      var items = $$("li", list);

      input.addEventListener("input", function () {
        var query = input.value.trim().toLowerCase();
        var shown = 0;

        items.forEach(function (item) {
          var link = $("[data-city-name]", item) || item;
          var haystack = (link.getAttribute("data-city-name") || item.textContent).toLowerCase();
          var match = !query || haystack.indexOf(query) !== -1;
          item.classList.toggle("is-hidden", !match);
          if (match) shown++;
        });

        if (empty) empty.hidden = shown !== 0;
      });
    });
  })();

  /* ---------------------------------------------------------------- 5. */
  (function faqAccordion() {
    var groups = $$("[data-faq-group]");
    if (!groups.length) return;

    groups.forEach(function (group) {
      var items = $$("[data-faq]", group);

      items.forEach(function (item) {
        var summary = $("summary", item);
        var panel = $(".faq__a", item);
        if (!summary || !panel) return;

        // Items rendered open start at their natural height.
        panel.style.height = item.open ? "auto" : "0px";

        function expand() {
          item.open = true;
          panel.style.height = "0px";
          requestAnimationFrame(function () {
            panel.style.height = panel.scrollHeight + "px";
          });
          panel.addEventListener("transitionend", function done(event) {
            if (event.propertyName !== "height") return;
            panel.style.height = "auto";
            panel.removeEventListener("transitionend", done);
          });
        }

        function collapse() {
          panel.style.height = panel.scrollHeight + "px";
          requestAnimationFrame(function () {
            panel.style.height = "0px";
          });
          panel.addEventListener("transitionend", function done(event) {
            if (event.propertyName !== "height") return;
            item.open = false;
            panel.removeEventListener("transitionend", done);
          });
        }

        summary.addEventListener("click", function (event) {
          event.preventDefault();
          if (item.open) {
            collapse();
            return;
          }
          // Only one answer open per group.
          items.forEach(function (other) {
            if (other === item || !other.open) return;
            var otherPanel = $(".faq__a", other);
            otherPanel.style.height = otherPanel.scrollHeight + "px";
            requestAnimationFrame(function () { otherPanel.style.height = "0px"; });
            otherPanel.addEventListener("transitionend", function done(e) {
              if (e.propertyName !== "height") return;
              other.open = false;
              otherPanel.removeEventListener("transitionend", done);
            });
          });
          expand();
        });
      });
    });
  })();

  /* ---------------------------------------------------------------- 6. */
  (function carousels() {
    $$("[data-carousel]").forEach(function (root) {
      var viewport = $("[data-carousel-viewport]", root);
      var track = $("[data-carousel-track]", root);
      var slides = $$(".carousel__slide", track);
      var prev = $("[data-carousel-prev]", root);
      var next = $("[data-carousel-next]", root);
      var dotsWrap = $("[data-carousel-dots]", root);
      if (!viewport || !track || slides.length < 2) return;

      var index = 0;
      var maxIndex = 0;
      var timer = null;
      var delay = parseInt(root.getAttribute("data-carousel-autoplay"), 10) || 0;

      function offsetOf(i) {
        return slides[i].offsetLeft - slides[0].offsetLeft;
      }

      function measure() {
        // Measured from the slides themselves rather than track.scrollWidth,
        // which is unreliable on a transformed, overflowing flex container.
        var last = slides[slides.length - 1];
        var content = offsetOf(slides.length - 1) + last.offsetWidth;
        var maxScroll = Math.max(0, content - viewport.clientWidth);
        maxIndex = slides.length - 1;
        for (var i = 0; i < slides.length; i++) {
          if (offsetOf(i) >= maxScroll - 1) { maxIndex = i; break; }
        }
        if (index > maxIndex) index = maxIndex;
        buildDots();
        apply();
      }

      function apply() {
        track.style.transform = "translateX(-" + offsetOf(index) + "px)";
        slides.forEach(function (slide, i) {
          // Off-screen slides stay out of the tab order.
          var visible = i >= index && offsetOf(i) < offsetOf(index) + viewport.clientWidth - 1;
          slide.setAttribute("aria-hidden", visible ? "false" : "true");
          $$("a, button", slide).forEach(function (el) {
            if (visible) el.removeAttribute("tabindex"); else el.setAttribute("tabindex", "-1");
          });
        });
        if (dotsWrap) {
          $$(".carousel__dot", dotsWrap).forEach(function (dot, i) {
            dot.classList.toggle("is-active", i === index);
            dot.setAttribute("aria-current", i === index ? "true" : "false");
          });
        }
      }

      function goTo(i) {
        index = Math.max(0, Math.min(i, maxIndex));
        apply();
      }

      function buildDots() {
        if (!dotsWrap) return;
        dotsWrap.innerHTML = "";
        for (var i = 0; i <= maxIndex; i++) {
          (function (target) {
            var dot = document.createElement("button");
            dot.type = "button";
            dot.className = "carousel__dot";
            dot.setAttribute("aria-label", "Go to review " + (target + 1));
            dot.addEventListener("click", function () { goTo(target); restart(); });
            dotsWrap.appendChild(dot);
          })(i);
        }
      }

      function step(direction) {
        var target = index + direction;
        if (target > maxIndex) target = 0;
        if (target < 0) target = maxIndex;
        goTo(target);
      }

      function start() {
        if (!delay || reducedMotion.matches) return;
        stop();
        timer = window.setInterval(function () { step(1); }, delay);
      }
      function stop() { if (timer) { window.clearInterval(timer); timer = null; } }
      function restart() { stop(); start(); }

      if (prev) prev.addEventListener("click", function () { step(-1); restart(); });
      if (next) next.addEventListener("click", function () { step(1); restart(); });

      root.addEventListener("mouseenter", stop);
      root.addEventListener("mouseleave", start);
      root.addEventListener("focusin", stop);
      root.addEventListener("focusout", start);
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) stop(); else start();
      });

      // Touch / pointer swipe.
      var startX = null;
      viewport.addEventListener("pointerdown", function (event) {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        startX = event.clientX;
        stop();
      });
      viewport.addEventListener("pointerup", function (event) {
        if (startX === null) return;
        var dx = event.clientX - startX;
        startX = null;
        if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1);
        start();
      });
      viewport.addEventListener("pointercancel", function () { startX = null; start(); });

      window.addEventListener("resize", debounce(measure, 180));
      measure();
      start();
    });
  })();

  /* ---------------------------------------------------------------- 7. */
  (function scrollerArrows() {
    $$("[data-scroller-prev], [data-scroller-next]").forEach(function (button) {
      var key = button.getAttribute("data-scroller-prev") || button.getAttribute("data-scroller-next");
      var back = button.hasAttribute("data-scroller-prev");
      var scroller = $('[data-scroller="' + key + '"]');
      if (!scroller) return;

      button.addEventListener("click", function () {
        var amount = Math.max(240, scroller.clientWidth * 0.8);
        scroller.scrollBy({
          left: back ? -amount : amount,
          behavior: reducedMotion.matches ? "auto" : "smooth"
        });
      });
    });
  })();

  /* ---------------------------------------------------------------- 8. */
  (function scrollReveal() {
    var targets = $$("[data-reveal]");
    if (!targets.length) return;

    if (!("IntersectionObserver" in window) || reducedMotion.matches) {
      targets.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -12% 0px", threshold: 0.06 });

    targets.forEach(function (el) { observer.observe(el); });
  })();

  /* ---------------------------------------------------------------- 9. */
  (function galleryAndLightbox() {
    var gallery = $("[data-gallery]");
    if (!gallery) return;

    var stage = $("[data-gallery-stage]", gallery);
    var thumbs = $$("[data-gallery-src]", gallery);
    var current = 0;

    function show(i) {
      var thumb = thumbs[i];
      if (!thumb || !stage) return;
      current = i;
      stage.src = thumb.getAttribute("data-gallery-src");
      stage.alt = thumb.getAttribute("data-gallery-alt") || "";
      thumbs.forEach(function (other, index) {
        other.classList.toggle("is-active", index === i);
      });
    }

    thumbs.forEach(function (thumb, i) {
      thumb.addEventListener("click", function () { show(i); });
    });

    /* -- lightbox -- */
    var box = $("[data-lightbox]");
    if (!box) return;

    var image = $("[data-lightbox-image]", box);
    var caption = $("[data-lightbox-caption]", box);
    var openers = $$("[data-lightbox-open]");
    var closeBtn = $("[data-lightbox-close]", box);
    var lastFocused = null;

    function paint(i) {
      var thumb = thumbs[i];
      if (!thumb) return;
      current = i;
      image.src = thumb.getAttribute("data-gallery-src");
      image.alt = thumb.getAttribute("data-gallery-alt") || "";
      caption.textContent = "Photo " + (i + 1) + " of " + thumbs.length;
      show(i);
    }

    function openBox() {
      lastFocused = document.activeElement;
      box.hidden = false;
      requestAnimationFrame(function () { box.classList.add("is-open"); });
      paint(current);
      lockScroll(true);
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }

    function closeBox() {
      box.classList.remove("is-open");
      lockScroll(false);
      window.setTimeout(function () { box.hidden = true; }, 240);
      if (lastFocused) lastFocused.focus({ preventScroll: true });
    }

    function move(step) {
      paint((current + step + thumbs.length) % thumbs.length);
    }

    openers.forEach(function (btn) { btn.addEventListener("click", openBox); });
    if (closeBtn) closeBtn.addEventListener("click", closeBox);
    var prev = $("[data-lightbox-prev]", box);
    var next = $("[data-lightbox-next]", box);
    if (prev) prev.addEventListener("click", function () { move(-1); });
    if (next) next.addEventListener("click", function () { move(1); });

    box.addEventListener("click", function (event) {
      if (event.target === box) closeBox();
    });

    document.addEventListener("keydown", function (event) {
      if (box.hidden) return;
      if (event.key === "Escape") closeBox();
      if (event.key === "ArrowLeft") move(-1);
      if (event.key === "ArrowRight") move(1);
    });
  })();

  /* --------------------------------------------------------------- 10. */
  (function stickyBookingBar() {
    var bar = $("[data-sticky-bar]");
    var anchor = $(".booking");
    if (!bar || !anchor) return;

    bar.hidden = false;

    var visible = false;
    function update() {
      var rect = anchor.getBoundingClientRect();
      var passed = rect.bottom < 80;                 // scrolled past the panel
      var ahead = rect.top > window.innerHeight;     // panel still far below
      var should = passed || (ahead && window.scrollY > 400);
      if (should !== visible) {
        visible = should;
        bar.classList.toggle("is-visible", should);
      }
    }

    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", debounce(update, 150));
    update();

    var cta = $("[data-sticky-cta]", bar);
    if (cta) {
      cta.addEventListener("click", function (event) {
        event.preventDefault();
        anchor.scrollIntoView({
          behavior: reducedMotion.matches ? "auto" : "smooth",
          block: "center"
        });
        var firstField = $("select, input", anchor);
        if (firstField) window.setTimeout(function () { firstField.focus({ preventScroll: true }); }, 500);
      });
    }
  })();

  /* --------------------------------------------------------------- 11. */
  (function listingControls() {
    // Filter drawer (small screens only; from 1024px the panel is static).
    var toggle = $("[data-filters-toggle]");
    var panel = $("#filters");
    var scrim = $("[data-filters-scrim]");

    if (toggle && panel && scrim) {
      var openFilters = function () {
        scrim.hidden = false;
        requestAnimationFrame(function () {
          panel.classList.add("is-open");
          scrim.classList.add("is-open");
        });
        toggle.setAttribute("aria-expanded", "true");
        lockScroll(true);
      };
      var closeFilters = function () {
        if (toggle.getAttribute("aria-expanded") !== "true") return;
        panel.classList.remove("is-open");
        scrim.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        lockScroll(false);
        window.setTimeout(function () {
          if (!scrim.classList.contains("is-open")) scrim.hidden = true;
        }, 420);
      };

      toggle.addEventListener("click", openFilters);
      scrim.addEventListener("click", closeFilters);
      var closeBtn = $("[data-filters-close]", panel);
      if (closeBtn) closeBtn.addEventListener("click", closeFilters);
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeFilters();
      });
    }

    // Budget slider readout.
    var range = $("[data-range-input]");
    var output = $("[data-range-output]");
    if (range && output) {
      range.addEventListener("input", function () {
        output.textContent = money(range.value);
      });
    }

    // Sort dropdown submits its form on change.
    $$("[data-autosubmit]").forEach(function (select) {
      select.addEventListener("change", function () {
        if (select.form) select.form.submit();
      });
    });
  })();

  /* --------------------------------------------------------------- 12. */
  (function cart() {
    var lines = $$("[data-cart-line]");
    if (!lines.length) return;

    var FREE_DELIVERY_OVER = 3000;
    var DELIVERY_FEE = 249;
    var TAX_RATE = 0.18;

    function recalc() {
      var subtotal = 0;
      var savings = 0;

      $$("[data-cart-line]").forEach(function (line) {
        var stepper = $("[data-stepper]", line);
        var totalEl = $("[data-line-total]", line);
        if (!stepper || !totalEl) return;

        var qty = parseInt($("[data-stepper-input]", stepper).value, 10) || 1;
        var unit = parseFloat(stepper.getAttribute("data-unit-price")) || 0;
        var unitSaving = parseFloat(stepper.getAttribute("data-unit-saving")) || 0;

        totalEl.textContent = money(unit * qty);
        subtotal += unit * qty;
        savings += unitSaving * qty;
      });

      var delivery = subtotal >= FREE_DELIVERY_OVER || subtotal === 0 ? 0 : DELIVERY_FEE;
      var tax = Math.round(subtotal * TAX_RATE);

      var write = function (key, value) {
        var el = $('[data-summary="' + key + '"]');
        if (el) el.textContent = value;
      };
      write("subtotal", money(subtotal));
      write("savings", "− " + money(savings));
      write("delivery", delivery ? money(delivery) : "Free");
      write("tax", money(tax));
      write("total", money(subtotal + delivery + tax));
    }

    $$("[data-stepper]").forEach(function (stepper) {
      var input = $("[data-stepper-input]", stepper);
      var down = $("[data-stepper-down]", stepper);
      var up = $("[data-stepper-up]", stepper);
      if (!input) return;

      var nudge = function (delta) {
        var min = parseInt(input.min, 10) || 1;
        var max = parseInt(input.max, 10) || 99;
        var next = (parseInt(input.value, 10) || min) + delta;
        input.value = Math.max(min, Math.min(max, next));
        recalc();
      };

      if (down) down.addEventListener("click", function () { nudge(-1); });
      if (up) up.addEventListener("click", function () { nudge(1); });
      input.addEventListener("change", recalc);
    });

    $$("[data-cart-remove]").forEach(function (button) {
      button.addEventListener("click", function () {
        var line = button.closest("[data-cart-line]");
        if (!line) return;
        line.classList.add("is-removing");
        window.setTimeout(function () {
          line.remove();
          recalc();
          if (window.Celebra) window.Celebra.toast("Removed from cart");
        }, 240);
      });
    });

    recalc();
  })();

  /* --------------------------------------------------------------- 13. */
  var toastEl = null;
  var toastTimer = null;

  function toast(message) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "toast";
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      toastEl.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-check-circle"></use></svg><span></span>';
      document.body.appendChild(toastEl);
    }
    $("span", toastEl).textContent = message;
    requestAnimationFrame(function () { toastEl.classList.add("is-visible"); });
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      toastEl.classList.remove("is-visible");
    }, 2600);
  }

  window.Celebra = { toast: toast };

  $$("[data-add-to-cart]").forEach(function (button) {
    button.addEventListener("click", function () {
      // Placeholder until the cart backend exists: confirm, then send them on.
      toast("Added to cart. Pick a slot at checkout.");
    });
  });
})();
