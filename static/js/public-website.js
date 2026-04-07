(() => {
  const header = document.querySelector("[data-public-header]");
  const onScroll = () => {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 24);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const slides = [...document.querySelectorAll(".public-hero-slide")];
  if (slides.length > 1) {
    let current = 0;
    window.setInterval(() => {
      slides[current].classList.remove("is-active");
      current = (current + 1) % slides.length;
      slides[current].classList.add("is-active");
    }, 5200);
  }

  const revealItems = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && revealItems.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.16 });
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  const drawer = document.querySelector("[data-mobile-drawer]");
  const backdrop = document.querySelector("[data-mobile-backdrop]");
  const openDrawer = () => {
    drawer?.classList.add("is-open");
    backdrop?.classList.add("is-open");
    document.body.style.overflow = "hidden";
  };
  const closeDrawer = () => {
    drawer?.classList.remove("is-open");
    backdrop?.classList.remove("is-open");
    document.body.style.overflow = "";
  };
  document.querySelector("[data-mobile-menu-open]")?.addEventListener("click", openDrawer);
  document.querySelector("[data-mobile-menu-close]")?.addEventListener("click", closeDrawer);
  backdrop?.addEventListener("click", closeDrawer);

  const searchModal = document.querySelector("[data-search-modal]");
  const searchInput = document.querySelector("[data-search-input]");
  const searchItems = [...document.querySelectorAll("[data-search-item]")];
  const openSearch = () => {
    searchModal?.classList.add("is-open");
    document.body.style.overflow = "hidden";
    window.setTimeout(() => searchInput?.focus(), 60);
  };
  const closeSearch = () => {
    searchModal?.classList.remove("is-open");
    document.body.style.overflow = "";
    if (searchInput) searchInput.value = "";
    searchItems.forEach((item) => (item.hidden = false));
  };
  document.querySelector("[data-search-open]")?.addEventListener("click", openSearch);
  document.querySelector("[data-search-close]")?.addEventListener("click", closeSearch);
  searchModal?.addEventListener("click", (event) => {
    if (event.target === searchModal) closeSearch();
  });
  searchInput?.addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    searchItems.forEach((item) => {
      item.hidden = !item.textContent.toLowerCase().includes(query);
    });
  });

  const magneticButtons = document.querySelectorAll(".magnetic");
  magneticButtons.forEach((button) => {
    button.addEventListener("mousemove", (event) => {
      const rect = button.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      button.style.transform = `translate(${x * 0.08}px, ${y * 0.08}px)`;
    });
    button.addEventListener("mouseleave", () => {
      button.style.transform = "";
    });
  });

  const chatbot = document.querySelector("[data-chatbot]");
  const chatbotLog = document.querySelector("[data-chatbot-log]");
  const chatbotForm = document.querySelector("[data-chatbot-form]");
  const chatbotInput = chatbotForm?.querySelector("input");
  const chatbotReply = (message) => {
    const text = message.toLowerCase();
    if (text.includes("exam")) {
      return "Entrance examinations are usually organised in March, May, July, and August, subject to school confirmation. You can begin from the registration page.";
    }
    if (text.includes("boarding") || text.includes("hostel")) {
      return "NDGA offers a supervised boarding environment that supports study, routine, and student welfare. Open the hostel page for more details.";
    }
    if (text.includes("apply") || text.includes("admission") || text.includes("register")) {
      return "You can begin the process on the online registration page. Prepare a passport photograph, birth certificate, and recent school result.";
    }
    if (text.includes("direction") || text.includes("map") || text.includes("location")) {
      return "The school is at Kuchiyako, Kuje-Abuja. Use the map or contact page to open directions.";
    }
    if (text.includes("contact") || text.includes("phone") || text.includes("email")) {
      return "You can contact the school through +234 902 940 5413, +234 813 341 3127, or office@ndgakuje.org.";
    }
    return "I can help with admissions, boarding, entrance exams, fees, and contact support. Try one of the quick prompts or open the contact page.";
  };
  const addChatMessage = (text, type) => {
    if (!chatbotLog) return;
    const article = document.createElement("article");
    article.className = type === "user" ? "is-user" : "is-bot";
    article.textContent = text;
    chatbotLog.appendChild(article);
    chatbotLog.scrollTop = chatbotLog.scrollHeight;
  };
  const openChatbot = () => chatbot?.classList.add("is-open");
  const closeChatbot = () => chatbot?.classList.remove("is-open");
  document.querySelector("[data-chatbot-open]")?.addEventListener("click", openChatbot);
  document.querySelector("[data-chatbot-close]")?.addEventListener("click", closeChatbot);
  document.querySelectorAll("[data-chatbot-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-chatbot-chip") || "";
      openChatbot();
      addChatMessage(text, "user");
      addChatMessage(chatbotReply(text), "bot");
    });
  });
  chatbotForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = chatbotInput?.value.trim();
    if (!text) return;
    openChatbot();
    addChatMessage(text, "user");
    addChatMessage(chatbotReply(text), "bot");
    chatbotInput.value = "";
  });

  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImage = document.querySelector("[data-lightbox-target]");
  const lightboxCaption = document.querySelector("[data-lightbox-caption]");
  document.querySelectorAll("[data-lightbox-image]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!lightbox || !lightboxImage) return;
      lightboxImage.src = button.getAttribute("data-lightbox-image") || "";
      lightboxImage.alt = button.getAttribute("data-lightbox-title") || "";
      if (lightboxCaption) {
        lightboxCaption.textContent = button.getAttribute("data-lightbox-title") || "";
      }
      lightbox.classList.add("is-open");
      document.body.style.overflow = "hidden";
    });
  });
  const closeLightbox = () => {
    lightbox?.classList.remove("is-open");
    document.body.style.overflow = "";
  };
  document.querySelector("[data-lightbox-close]")?.addEventListener("click", closeLightbox);
  lightbox?.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });

  const form = document.querySelector("[data-multi-step-form]");
  if (form) {
    const steps = [...form.querySelectorAll("[data-form-step]")];
    const nextButton = form.querySelector("[data-step-next]");
    const backButton = form.querySelector("[data-step-back]");
    const submitButton = form.querySelector("[data-step-submit]");
    let stepIndex = 0;
    const updateSteps = () => {
      steps.forEach((step, index) => step.classList.toggle("is-active", index === stepIndex));
      if (backButton) backButton.hidden = stepIndex === 0;
      if (nextButton) nextButton.hidden = stepIndex === steps.length - 1;
      if (submitButton) submitButton.hidden = stepIndex !== steps.length - 1;
    };
    nextButton?.addEventListener("click", () => {
      if (stepIndex < steps.length - 1) {
        stepIndex += 1;
        updateSteps();
      }
    });
    backButton?.addEventListener("click", () => {
      if (stepIndex > 0) {
        stepIndex -= 1;
        updateSteps();
      }
    });
    updateSteps();
  }

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
      closeSearch();
      closeChatbot();
      closeLightbox();
    }
  });
})();
