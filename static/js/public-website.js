(() => {
  const body = document.body;
  const header = document.querySelector("[data-public-header]");
  const drawer = document.querySelector("[data-mobile-drawer]");
  const backdrop = document.querySelector("[data-mobile-backdrop]");
  const searchModal = document.querySelector("[data-search-modal]");
  const searchInput = document.querySelector("[data-search-input]");
  const searchItems = [...document.querySelectorAll("[data-search-item]")];
  const chatbot = document.querySelector("[data-chatbot]");
  const chatbotLog = document.querySelector("[data-chatbot-log]");
  const chatbotForm = document.querySelector("[data-chatbot-form]");
  const chatbotInput = chatbotForm?.querySelector("input");
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImage = document.querySelector("[data-lightbox-target]");
  const lightboxCaption = document.querySelector("[data-lightbox-caption]");
  const liveChat = document.querySelector("[data-live-chat]");
  const liveChatForm = document.querySelector("[data-live-chat-form]");
  const liveChatStatus = document.querySelector("[data-live-chat-status]");
  const liveChatThread = document.querySelector("[data-live-chat-thread]");

  const lockBody = (locked) => {
    body.style.overflow = locked ? "hidden" : "";
  };

  const onScroll = () => {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 24);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const revealItems = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && revealItems.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.14 });
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  const navItems = [...document.querySelectorAll("[data-nav-item]")];
  navItems.forEach((item) => {
    let timeoutId = null;
    const open = () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      item.classList.add("is-open");
    };
    const close = () => {
      timeoutId = window.setTimeout(() => {
        item.classList.remove("is-open");
      }, 160);
    };
    item.addEventListener("mouseenter", open);
    item.addEventListener("mouseleave", close);
    item.addEventListener("focusin", open);
    item.addEventListener("focusout", close);
  });

  const openDrawer = () => {
    drawer?.classList.add("is-open");
    backdrop?.classList.add("is-open");
    lockBody(true);
  };
  const closeDrawer = () => {
    drawer?.classList.remove("is-open");
    backdrop?.classList.remove("is-open");
    lockBody(false);
  };
  document.querySelector("[data-mobile-menu-open]")?.addEventListener("click", openDrawer);
  document.querySelector("[data-mobile-menu-close]")?.addEventListener("click", closeDrawer);
  backdrop?.addEventListener("click", closeDrawer);

  const openSearch = () => {
    searchModal?.classList.add("is-open");
    lockBody(true);
    window.setTimeout(() => searchInput?.focus(), 80);
  };
  const closeSearch = () => {
    searchModal?.classList.remove("is-open");
    lockBody(false);
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

  document.querySelectorAll(".magnetic").forEach((button) => {
    button.addEventListener("mousemove", (event) => {
      const rect = button.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      button.style.transform = `translate(${x * 0.06}px, ${y * 0.06}px)`;
    });
    button.addEventListener("mouseleave", () => {
      button.style.transform = "";
    });
  });

  const chatbotReply = (message) => {
    const text = message.toLowerCase();
    if (text.includes("exam")) {
      return "Entrance examinations are usually organised across March, May, July, and August, subject to school confirmation for each cycle.";
    }
    if (text.includes("boarding") || text.includes("hostel")) {
      return "NDGA is a boarding school with supervised routine, prep time, student welfare support, and clear hostel guidance for families.";
    }
    if (text.includes("apply") || text.includes("admission") || text.includes("register")) {
      return "You can begin from the online registration page. The main screening subjects are English Language, Mathematics, and General Paper.";
    }
    if (text.includes("fee") || text.includes("payment")) {
      return "The fee page shows the class-by-class structure, while the latest approved amount is issued through admissions and bursary guidance.";
    }
    if (text.includes("direction") || text.includes("map") || text.includes("location")) {
      return "The school is just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje-Abuja. Use the map button to open directions.";
    }
    if (text.includes("contact") || text.includes("phone") || text.includes("email")) {
      return "You can reach the school through +234 902 940 5413, +234 813 341 3127, or office@ndgakuje.org.";
    }
    return "I can help with admissions, fees, boarding, entrance exams, directions, and contact support. Try one of the quick prompts.";
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

  const openLightbox = (button) => {
    if (!lightbox || !lightboxImage) return;
    lightboxImage.src = button.getAttribute("data-lightbox-image") || "";
    lightboxImage.alt = button.getAttribute("data-lightbox-title") || "";
    if (lightboxCaption) {
      lightboxCaption.textContent = button.getAttribute("data-lightbox-title") || "";
    }
    lightbox.classList.add("is-open");
    lockBody(true);
  };
  const closeLightbox = () => {
    lightbox?.classList.remove("is-open");
    lockBody(false);
  };
  document.querySelectorAll("[data-lightbox-image]").forEach((button) => {
    button.addEventListener("click", () => openLightbox(button));
  });
  document.querySelector("[data-lightbox-close]")?.addEventListener("click", closeLightbox);
  lightbox?.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });

  const openLiveChat = () => {
    liveChat?.classList.add("is-open");
  };
  const closeLiveChat = () => {
    liveChat?.classList.remove("is-open");
    if (liveChatStatus) liveChatStatus.textContent = "";
  };
  document.querySelectorAll("[data-live-chat-open]").forEach((button) => {
    button.addEventListener("click", openLiveChat);
  });
  document.querySelector("[data-live-chat-close]")?.addEventListener("click", closeLiveChat);

  const LIVE_CHAT_STORAGE_KEY = "ndga_public_live_chat_messages";

  const appendLiveChatBubble = (text, sender) => {
    if (!liveChatThread || !text) return;
    const item = document.createElement("article");
    item.className = `public-live-chat-bubble is-${sender}`;
    const title = document.createElement("strong");
    title.textContent = sender === "user" ? "Visitor" : "NDGA Admissions";
    const body = document.createElement("p");
    body.textContent = text;
    item.append(title, body);
    liveChatThread.appendChild(item);
    liveChatThread.scrollTop = liveChatThread.scrollHeight;
  };

  const saveLiveChatMessages = () => {
    if (!liveChatThread || !window.sessionStorage) return;
    const payload = [...liveChatThread.querySelectorAll(".public-live-chat-bubble")].slice(2).map((item) => ({
      sender: item.classList.contains("is-user") ? "user" : "agent",
      text: item.querySelector("p")?.textContent || "",
    }));
    window.sessionStorage.setItem(LIVE_CHAT_STORAGE_KEY, JSON.stringify(payload));
  };

  const loadLiveChatMessages = () => {
    if (!liveChatThread || !window.sessionStorage) return;
    try {
      const raw = window.sessionStorage.getItem(LIVE_CHAT_STORAGE_KEY);
      if (!raw) return;
      const messages = JSON.parse(raw);
      messages.forEach((message) => appendLiveChatBubble(message.text, message.sender));
    } catch (error) {
      window.sessionStorage.removeItem(LIVE_CHAT_STORAGE_KEY);
    }
  };

  loadLiveChatMessages();

  liveChatForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!liveChatForm || !liveChatStatus) return;
    const messageInput = liveChatForm.querySelector("textarea[name='message']");
    const messageText = messageInput?.value.trim();
    if (messageText) {
      appendLiveChatBubble(messageText, "user");
      saveLiveChatMessages();
    }
    liveChatStatus.textContent = "Sending...";
    const formData = new FormData(liveChatForm);
    try {
      const response = await fetch(liveChatForm.action, {
        method: "POST",
        body: formData,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        liveChatStatus.textContent = "Please complete the required fields and try again.";
        if (liveChatThread) {
          const bubbles = liveChatThread.querySelectorAll(".public-live-chat-bubble.is-user");
          bubbles[bubbles.length - 1]?.remove();
          saveLiveChatMessages();
        }
        return;
      }
      liveChatForm.reset();
      appendLiveChatBubble(payload.message || "Your message has been sent to the admissions desk.", "agent");
      saveLiveChatMessages();
      liveChatStatus.textContent = payload.message || "Your message has been sent.";
    } catch (error) {
      liveChatStatus.textContent = "Unable to send right now. Please try again.";
      if (liveChatThread) {
        const bubbles = liveChatThread.querySelectorAll(".public-live-chat-bubble.is-user");
        bubbles[bubbles.length - 1]?.remove();
        saveLiveChatMessages();
      }
    }
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
      closeLiveChat();
    }
  });
})();
