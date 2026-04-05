document.addEventListener("DOMContentLoaded", function () {
  const header = document.getElementById("siteHeader");
  const drawer = document.getElementById("siteMobileDrawer");
  const backdrop = document.getElementById("siteMobileBackdrop");
  const openBtn = document.getElementById("siteMobileToggle");
  const closeBtn = document.getElementById("siteMobileClose");
  const lightbox = document.getElementById("siteLightbox");
  const lightboxClose = document.getElementById("siteLightboxClose");
  const lightboxImage = document.getElementById("siteLightboxImage");
  const lightboxTitle = document.getElementById("siteLightboxTitle");
  const lightboxCaption = document.getElementById("siteLightboxCaption");

  function syncHeader() {
    if (!header) {
      return;
    }
    header.classList.toggle("is-scrolled", window.scrollY > 18);
  }

  function closeDrawer() {
    if (!drawer || !backdrop || !openBtn) {
      return;
    }
    drawer.classList.remove("is-open");
    backdrop.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    openBtn.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  }

  function openDrawer() {
    if (!drawer || !backdrop || !openBtn) {
      return;
    }
    drawer.classList.add("is-open");
    backdrop.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    openBtn.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    if (!lightbox) {
      return;
    }
    lightbox.classList.remove("is-open");
    lightbox.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  if (openBtn) {
    openBtn.addEventListener("click", openDrawer);
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", closeDrawer);
  }
  if (backdrop) {
    backdrop.addEventListener("click", closeDrawer);
  }

  document.querySelectorAll(".site-mobile-nav a").forEach(function (link) {
    link.addEventListener("click", closeDrawer);
  });

  document.querySelectorAll("[data-assistant-panel]").forEach(function (panel) {
    const chips = panel.querySelectorAll("[data-assistant-target]");
    const responses = panel.querySelectorAll("[data-assistant-response]");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        const slug = chip.getAttribute("data-assistant-target");
        chips.forEach(function (item) {
          item.classList.toggle("is-active", item === chip);
        });
        responses.forEach(function (response) {
          response.classList.toggle("is-active", response.getAttribute("data-assistant-response") === slug);
        });
      });
    });
  });

  document.querySelectorAll(".gallery-card").forEach(function (card) {
    card.addEventListener("click", function () {
      if (!lightbox || !lightboxImage || !lightboxTitle || !lightboxCaption) {
        return;
      }
      lightboxImage.src = card.getAttribute("data-lightbox-image") || "";
      lightboxImage.alt = card.getAttribute("data-lightbox-title") || "";
      lightboxTitle.textContent = card.getAttribute("data-lightbox-title") || "";
      lightboxCaption.textContent = card.getAttribute("data-lightbox-caption") || "";
      lightbox.classList.add("is-open");
      lightbox.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    });
  });

  if (lightboxClose) {
    lightboxClose.addEventListener("click", closeLightbox);
  }
  if (lightbox) {
    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) {
        closeLightbox();
      }
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeDrawer();
      closeLightbox();
    }
  });

  const observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.16 }
  );

  document.querySelectorAll(".reveal").forEach(function (node) {
    observer.observe(node);
  });
});
