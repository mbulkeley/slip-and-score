/* Photo viewer that opens over the page instead of navigating to the image.
 *
 * Why: in the iPhone home-screen app there's no browser back button, so
 * opening a bare JPEG left you stranded. Links marked
 *   <a href="full.jpg" data-lightbox="group-name" data-caption="…">
 * open here instead; photos sharing a group can be swiped through.
 * Without JavaScript the links still work as plain links.
 */
(function () {
  "use strict";

  let box, img, caption, counter, prevBtn, nextBtn;
  let group = [];
  let index = 0;
  let touchX = null;
  let pushedState = false;

  function build() {
    box = document.createElement("div");
    box.className = "lightbox";
    box.hidden = true;
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Photo viewer");
    box.innerHTML =
      '<button type="button" class="lb-close" aria-label="Close">✕</button>' +
      '<button type="button" class="lb-prev" aria-label="Previous photo">‹</button>' +
      '<figure class="lb-figure"><img class="lb-img" alt=""><figcaption class="lb-caption"></figcaption></figure>' +
      '<button type="button" class="lb-next" aria-label="Next photo">›</button>' +
      '<div class="lb-counter" aria-live="polite"></div>';
    document.body.appendChild(box);

    img = box.querySelector(".lb-img");
    caption = box.querySelector(".lb-caption");
    counter = box.querySelector(".lb-counter");
    prevBtn = box.querySelector(".lb-prev");
    nextBtn = box.querySelector(".lb-next");

    box.querySelector(".lb-close").addEventListener("click", close);
    prevBtn.addEventListener("click", (e) => { e.stopPropagation(); show(index - 1); });
    nextBtn.addEventListener("click", (e) => { e.stopPropagation(); show(index + 1); });
    // Tap the dark background (not the photo) to close.
    box.addEventListener("click", (e) => { if (e.target === box || e.target.classList.contains("lb-figure")) close(); });

    box.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", (e) => {
      if (touchX === null) return;
      const dx = e.changedTouches[0].clientX - touchX;
      touchX = null;
      if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
    });
  }

  function show(i) {
    if (!group.length) return;
    index = (i + group.length) % group.length;
    const link = group[index];
    img.src = link.href;
    img.alt = link.dataset.caption || "";
    caption.textContent = link.dataset.caption || "";
    caption.hidden = !link.dataset.caption;
    const many = group.length > 1;
    prevBtn.hidden = nextBtn.hidden = counter.hidden = !many;
    counter.textContent = many ? `${index + 1} / ${group.length}` : "";
    // Warm the neighbours so swiping feels instant.
    if (many) [index + 1, index - 1].forEach((n) => { new Image().src = group[(n + group.length) % group.length].href; });
  }

  function open(link) {
    if (!box) build();
    const name = link.dataset.lightbox;
    group = Array.from(document.querySelectorAll(`a[data-lightbox="${CSS.escape(name)}"]`));
    box.hidden = false;
    document.documentElement.classList.add("lb-open");
    show(group.indexOf(link));
    box.querySelector(".lb-close").focus({ preventScroll: true });
    // Let the browser/Android back gesture close the viewer instead of leaving the page.
    history.pushState({ lightbox: true }, "");
    pushedState = true;
  }

  function close() {
    if (!box || box.hidden) return;
    box.hidden = true;
    img.removeAttribute("src");
    document.documentElement.classList.remove("lb-open");
    if (pushedState) {
      pushedState = false;
      history.back();
    }
  }

  window.addEventListener("popstate", () => {
    if (pushedState) {
      pushedState = false;
      close();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (!box || box.hidden) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") show(index + 1);
    else if (e.key === "ArrowLeft") show(index - 1);
  });

  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-lightbox]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey) return; // allow open-in-new-tab
    e.preventDefault();
    open(link);
  });
})();
