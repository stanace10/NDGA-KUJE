document.addEventListener("DOMContentLoaded", function () {
  const header = document.getElementById("siteHeader");
  const mobileDrawer = document.getElementById("siteMobileDrawer");
  const mobileBackdrop = document.getElementById("siteMobileBackdrop");
  const mobileOpen = document.getElementById("siteMobileToggle");
  const mobileClose = document.getElementById("siteMobileClose");
  const searchPanel = document.getElementById("siteSearchPanel");
  const searchBackdrop = document.getElementById("siteSearchBackdrop");
  const searchOpen = document.getElementById("siteSearchToggle");
  const searchClose = document.getElementById("siteSearchClose");
  const searchInput = document.getElementById("siteSearchInput");
  const searchLinks = document.querySelectorAll(".site-search-link");
  const assistant = document.getElementById("siteAssistantPanel");
  const assistantOpen = document.getElementById("siteAssistantToggle");
  const assistantClose = document.getElementById("siteAssistantClose");
  const assistantInput = document.getElementById("assistantPrompt");
  const assistantAskButton = document.getElementById("assistantAskButton");
  const assistantHelper = document.getElementById("assistantHelper");
  const lightbox = document.getElementById("siteLightbox");
  const lightboxClose = document.getElementById("siteLightboxClose");
  const lightboxImage = document.getElementById("siteLightboxImage");
  const lightboxTitle = document.getElementById("siteLightboxTitle");
  const lightboxCaption = document.getElementById("siteLightboxCaption");

  const assistantRules = [
    { keywords: ["fee", "fees", "charge", "payment"], slug: "fees", helper: "The fees page explains the fee structure and payment guidance." },
    { keywords: ["board", "boarding", "hostel", "accommodation"], slug: "boarding", helper: "Boarding guidance stays visible before registration and the school confirms specific follow-up directly." },
    { keywords: ["screen", "exam", "date", "screening"], slug: "screening", helper: "Screening details are released by the school when the intake schedule is ready." },
    { keywords: ["apply", "registration", "register", "admission"], slug: "apply", helper: "Admissions starts on the public registration pages, not inside the portal." },
    { keywords: ["portal", "login", "support", "contact"], slug: "contact", helper: "The portal is secondary. Contact the school directly if you need help before or after registration." },
  ];

  function setBodyLock(locked) {
    document.body.style.overflow = locked ? "hidden" : "";
  }

  function syncHeader() {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 18);
  }

  function openMobileDrawer() {
    if (!mobileDrawer || !mobileBackdrop || !mobileOpen) return;
    mobileDrawer.classList.add("is-open");
    mobileBackdrop.classList.add("is-open");
    mobileDrawer.setAttribute("aria-hidden", "false");
    mobileOpen.setAttribute("aria-expanded", "true");
    setBodyLock(true);
  }

  function closeMobileDrawer() {
    if (!mobileDrawer || !mobileBackdrop || !mobileOpen) return;
    mobileDrawer.classList.remove("is-open");
    mobileBackdrop.classList.remove("is-open");
    mobileDrawer.setAttribute("aria-hidden", "true");
    mobileOpen.setAttribute("aria-expanded", "false");
    setBodyLock(false);
  }

  function openSearchPanel() {
    if (!searchPanel || !searchOpen) return;
    searchPanel.classList.add("is-open");
    searchPanel.setAttribute("aria-hidden", "false");
    searchOpen.setAttribute("aria-expanded", "true");
    setBodyLock(true);
    if (searchInput) {
      window.setTimeout(function () {
        searchInput.focus();
      }, 60);
    }
  }

  function closeSearchPanel() {
    if (!searchPanel || !searchOpen) return;
    searchPanel.classList.remove("is-open");
    searchPanel.setAttribute("aria-hidden", "true");
    searchOpen.setAttribute("aria-expanded", "false");
    setBodyLock(false);
  }

  function openAssistant() {
    if (!assistant || !assistantOpen) return;
    assistant.classList.add("is-open");
    assistant.setAttribute("aria-hidden", "false");
    assistantOpen.setAttribute("aria-expanded", "true");
  }

  function closeAssistant() {
    if (!assistant || !assistantOpen) return;
    assistant.classList.remove("is-open");
    assistant.setAttribute("aria-hidden", "true");
    assistantOpen.setAttribute("aria-expanded", "false");
  }

  function closeLightbox() {
    if (!lightbox) return;
    lightbox.classList.remove("is-open");
    lightbox.setAttribute("aria-hidden", "true");
    setBodyLock(false);
  }

  function activateAssistantSlug(slug, helperText) {
    if (!assistant) return;
    const chips = assistant.querySelectorAll("[data-assistant-target]");
    const responses = assistant.querySelectorAll("[data-assistant-response]");

    chips.forEach(function (chip) {
      chip.classList.toggle("is-active", chip.getAttribute("data-assistant-target") === slug);
    });
    responses.forEach(function (response) {
      response.classList.toggle("is-active", response.getAttribute("data-assistant-response") === slug);
    });
    if (assistantHelper && helperText) {
      assistantHelper.textContent = helperText;
    }
  }

  function handleAssistantAsk() {
    if (!assistantInput) return;
    const query = assistantInput.value.trim().toLowerCase();
    if (!query) return;

    const match = assistantRules.find(function (rule) {
      return rule.keywords.some(function (keyword) {
        return query.includes(keyword);
      });
    });

    if (match) {
      activateAssistantSlug(match.slug, match.helper);
    } else if (assistantHelper) {
      assistantHelper.textContent = "Use one of the quick prompts above or contact the school directly for a more specific answer.";
    }
  }

  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  if (mobileOpen) mobileOpen.addEventListener("click", openMobileDrawer);
  if (mobileClose) mobileClose.addEventListener("click", closeMobileDrawer);
  if (mobileBackdrop) mobileBackdrop.addEventListener("click", closeMobileDrawer);

  document.querySelectorAll(".site-mobile-nav a").forEach(function (link) {
    link.addEventListener("click", closeMobileDrawer);
  });

  if (searchOpen) searchOpen.addEventListener("click", openSearchPanel);
  if (searchClose) searchClose.addEventListener("click", closeSearchPanel);
  if (searchBackdrop) searchBackdrop.addEventListener("click", closeSearchPanel);

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      const value = searchInput.value.trim().toLowerCase();
      searchLinks.forEach(function (link) {
        const text = (link.getAttribute("data-search-text") || "") + " " + link.textContent.toLowerCase();
        const visible = !value || text.includes(value);
        link.style.display = visible ? "" : "none";
      });
    });
  }

  if (assistantOpen) {
    assistantOpen.addEventListener("click", function () {
      if (assistant && assistant.classList.contains("is-open")) {
        closeAssistant();
      } else {
        openAssistant();
      }
    });
  }
  if (assistantClose) assistantClose.addEventListener("click", closeAssistant);
  if (assistantAskButton) assistantAskButton.addEventListener("click", handleAssistantAsk);
  if (assistantInput) {
    assistantInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        handleAssistantAsk();
      }
    });
  }

  document.querySelectorAll("[data-assistant-target]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      activateAssistantSlug(chip.getAttribute("data-assistant-target"));
    });
  });

  document.querySelectorAll(".gallery-card").forEach(function (card) {
    card.addEventListener("click", function () {
      if (!lightbox || !lightboxImage || !lightboxTitle || !lightboxCaption) return;
      lightboxImage.src = card.getAttribute("data-lightbox-image") || "";
      lightboxImage.alt = card.getAttribute("data-lightbox-title") || "";
      lightboxTitle.textContent = card.getAttribute("data-lightbox-title") || "";
      lightboxCaption.textContent = card.getAttribute("data-lightbox-caption") || "";
      lightbox.classList.add("is-open");
      lightbox.setAttribute("aria-hidden", "false");
      setBodyLock(true);
    });
  });

  if (lightboxClose) lightboxClose.addEventListener("click", closeLightbox);
  if (lightbox) {
    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) closeLightbox();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMobileDrawer();
      closeSearchPanel();
      closeAssistant();
      closeLightbox();
    }
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );

    document.querySelectorAll(".reveal").forEach(function (node) {
      observer.observe(node);
    });
  } else {
    document.querySelectorAll(".reveal").forEach(function (node) {
      node.classList.add("is-visible");
    });
  }
});
