(() => {
  const body = document.body;
  const header = document.querySelector("[data-public-header]");
  const drawer = document.querySelector("[data-mobile-drawer]");
  const backdrop = document.querySelector("[data-mobile-backdrop]");
  const searchModal = document.querySelector("[data-search-modal]");
  const searchInput = document.querySelector("[data-search-input]");
  const searchItems = [...document.querySelectorAll("[data-search-item]")];
  const chatbot = document.querySelector("[data-chatbot]");
  const chatbotPayloadElement = document.getElementById("ndga-chatbot-payload");
  const chatToggleButtons = [...document.querySelectorAll("[data-chatbot-open]")];
  const chatbotScreens = [...document.querySelectorAll("[data-chatbot-screen]")];
  const chatbotNavButtons = [...document.querySelectorAll("[data-chatbot-nav]")];
  const chatbotCloseButtons = [...document.querySelectorAll("[data-chatbot-close]")];
  const chatbotBackButtons = [...document.querySelectorAll("[data-chatbot-back]")];
  const chatbotOpenMessageButtons = [...document.querySelectorAll("[data-chatbot-open-messages]")];
  const chatbotHomeActionButtons = [...document.querySelectorAll("[data-chatbot-home-action]")];
  const chatbotHomeLinkButtons = [...document.querySelectorAll("[data-chatbot-home-link]")];
  const chatbotLog = document.querySelector("[data-chatbot-log]");
  const chatbotForm = document.querySelector("[data-chatbot-form]");
  const chatbotInput = chatbotForm?.querySelector("input");
  const chatbotStatus = document.querySelector("[data-live-chat-status]");
  const supportWhatsappLink = document.querySelector(".ndga-support-fab--whatsapp");
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImage = document.querySelector("[data-lightbox-target]");
  const lightboxCaption = document.querySelector("[data-lightbox-caption]");
  const rotatingGalleries = [...document.querySelectorAll("[data-rotating-gallery]")];
  const announcementBar = document.querySelector("[data-announcement-bar]");

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

  if (announcementBar) {
    window.setTimeout(() => {
      announcementBar.classList.add("is-dismissed");
    }, 8000);
  }

  const chatbotPayload = (() => {
    if (!chatbotPayloadElement) return {};
    try {
      return JSON.parse(chatbotPayloadElement.textContent || "{}");
    } catch (error) {
      return {};
    }
  })();

  const chatbotKnowledge = Array.isArray(chatbotPayload.answers) ? chatbotPayload.answers : [];
  const chatbotFallback = chatbotPayload.fallback || {};
  const chatbotLiveChatUrl = chatbot?.getAttribute("data-live-chat-url") || "";
  const chatbotCsrfToken = chatbot?.getAttribute("data-live-chat-csrf") || "";
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const greetingPattern = /^(hi|hello|hey|good morning|good afternoon|good evening)\b/;
  const fallbackReplies = [
    "I did not catch that clearly. Ask me about admissions, boarding, academics, school life, contact details, or the school location.",
    "I can help best with short NDGA questions like admissions, boarding, subjects, school life, or how to contact the school.",
    "Try a simple question such as how to apply, what boarding is like, where the school is, or how to contact admissions.",
  ];
  const clarificationReplies = [
    "I am here to answer NDGA questions. Ask about admissions, boarding, academics, school life, safeguarding, contact details, or directions.",
    "Please type a short school question so I can help properly. For example: how do I apply, what is boarding like, or where is NDGA located?",
  ];
  let fallbackReplyIndex = 0;
  let clarificationReplyIndex = 0;
  let contactFlow = { active: false, step: null, data: {} };

  const normalizeText = (value) =>
    (value || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

  const setChatStatus = (text = "") => {
    if (chatbotStatus) chatbotStatus.textContent = text;
  };

  const setActiveChatScreen = (screen) => {
    chatbotScreens.forEach((panel) => {
      panel.classList.toggle("is-active", panel.getAttribute("data-chatbot-screen") === screen);
    });
    chatbotNavButtons.forEach((button) => {
      button.classList.toggle("is-active", button.getAttribute("data-chatbot-nav") === screen);
    });
  };

  const openChatbot = (screen = "home") => {
    if (!chatbot) return;
    chatbot.classList.add("is-open");
    setActiveChatScreen(screen);
    if (screen === "messages") {
      window.setTimeout(() => chatbotInput?.focus(), 120);
    }
  };

  const closeChatbot = () => {
    chatbot?.classList.remove("is-open");
    setChatStatus("");
    chatbotInput?.blur();
  };

  const scrollChatToEnd = () => {
    if (!chatbotLog) return;
    chatbotLog.scrollTop = chatbotLog.scrollHeight;
  };

  const addChatMessage = (text, sender, options = {}) => {
    if (!chatbotLog || !text) return null;
    const article = document.createElement("article");
    article.className = `public-live-chat-bubble is-${sender}`;
    const title = document.createElement("strong");
    title.textContent = options.label || (sender === "user" ? "You" : "Smart NDGA");
    const body = document.createElement("p");
    body.textContent = text;
    article.append(title, body);
    chatbotLog.appendChild(article);
    scrollChatToEnd();
    return article;
  };

  const addTypingIndicator = () => {
    if (!chatbotLog) return null;
    const article = document.createElement("article");
    article.className = "public-live-chat-bubble is-agent is-typing";
    const title = document.createElement("strong");
    title.textContent = "Smart NDGA";
    const dots = document.createElement("div");
    dots.className = "ndga-support-typing-dots";
    dots.innerHTML = "<span></span><span></span><span></span>";
    article.append(title, dots);
    chatbotLog.appendChild(article);
    scrollChatToEnd();
    return article;
  };

  const addQuickReplies = (items = []) => {
    if (!chatbotLog || !items.length) return;
    const wrap = document.createElement("div");
    wrap.className = "ndga-support-quickreplies";
    items.slice(0, 3).forEach((item) => {
      if (!item?.label) return;
      if (item.url) {
        const anchor = document.createElement("a");
        anchor.href = item.url;
        anchor.textContent = item.label;
        if (/^https?:\/\//i.test(item.url)) {
          anchor.target = "_blank";
          anchor.rel = "noreferrer";
        }
        wrap.appendChild(anchor);
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.dataset.chatbotAction = item.action || "query";
      if (item.value) button.dataset.chatbotValue = item.value;
      wrap.appendChild(button);
    });
    chatbotLog.appendChild(wrap);
    scrollChatToEnd();
  };

  const baseQuickReplies = () => [
    { label: "Start Admission", url: "/admissions/registration/" },
    { label: "Ask a Question", action: "focus" },
    { label: "Talk to School", action: "lead" },
  ];

  const suggestionQuickReplies = (payload) => {
    const replies = [];
    (payload?.links || []).slice(0, 1).forEach((link) => {
      if (link?.label && link?.url) replies.push({ label: link.label, url: link.url });
    });
    if (replies.length < 3 && payload?.suggestions?.[0]) {
      replies.push({ label: payload.suggestions[0], action: "query", value: payload.suggestions[0] });
    }
    while (replies.length < 3) {
      const fallback = baseQuickReplies()[replies.length];
      if (!fallback) break;
      replies.push(fallback);
    }
    return replies;
  };

  const ensureChatIntro = () => {
    if (!chatbotLog || chatbotLog.querySelector(".public-live-chat-bubble")) return;
    addChatMessage("Hi. Ask me about admissions, boarding, school life, or contact details.", "agent");
    addQuickReplies(baseQuickReplies());
  };

  const nextFallbackReply = () => {
    const reply = fallbackReplies[fallbackReplyIndex % fallbackReplies.length];
    fallbackReplyIndex += 1;
    return reply;
  };

  const nextClarificationReply = () => {
    const reply = clarificationReplies[clarificationReplyIndex % clarificationReplies.length];
    clarificationReplyIndex += 1;
    return reply;
  };

  const scoreKnowledgeEntry = (query, entry) => {
    const normalizedQuery = normalizeText(query);
    if (!normalizedQuery) return -1;
    let score = 0;

    (entry.phrases || []).forEach((phrase) => {
      const normalizedPhrase = normalizeText(phrase);
      if (!normalizedPhrase) return;
      if (normalizedQuery === normalizedPhrase) score += 140;
      else if (normalizedQuery.includes(normalizedPhrase)) score += 72;
    });

    let keywordMatches = 0;
    (entry.keywords || []).forEach((keyword) => {
      const normalizedKeyword = normalizeText(keyword);
      if (!normalizedKeyword) return;
      if (normalizedQuery.includes(normalizedKeyword)) {
        keywordMatches += 1;
        score += normalizedKeyword.includes(" ") ? 18 : 9;
      }
    });

    if (keywordMatches === 1 && score < 20) score -= 6;
    return score;
  };

  const resolveSupportReply = (message) => {
    const normalizedMessage = normalizeText(message);
    const compactMessage = normalizedMessage.replace(/\s+/g, "");
    const tokenCount = normalizedMessage ? normalizedMessage.split(" ").filter(Boolean).length : 0;
    const explicitHumanRequest = /(^|\s)(talk to admissions|talk to school|talk to management|speak to someone|speak with someone|human agent|live chat|contact school|complaint|complain|report an issue|report issue)(\s|$)/.test(normalizedMessage);
    if (explicitHumanRequest) {
      return {
        reply: "I can help you send this directly to the school. What is your full name?",
        human: true,
      };
    }

    if (!normalizedMessage) {
      return {
        ...chatbotFallback,
        reply: nextClarificationReply(),
      };
    }

    if (greetingPattern.test(normalizedMessage)) {
      return {
        reply: "Hello. I can help with NDGA admissions, boarding, academics, school life, contact details, and directions. What would you like to know?",
        suggestions: [
          "How do I apply?",
          "Tell me about NDGA.",
          "What is boarding like?",
        ],
        links: [
          { label: "Admissions Overview", "url": "/admissions/" },
        ],
      };
    }

    if (compactMessage.length <= 2 || (/^[a-z]+$/.test(compactMessage) && compactMessage.length <= 5 && !/[aeiou]/.test(compactMessage))) {
      return {
        ...chatbotFallback,
        reply: nextClarificationReply(),
      };
    }

    const ranked = chatbotKnowledge
      .map((entry) => ({ entry, score: scoreKnowledgeEntry(normalizedMessage, entry) }))
      .sort((left, right) => right.score - left.score);

    if (ranked[0] && ranked[0].score >= 18) return ranked[0].entry;
    if (ranked[0] && ranked[0].score >= 10 && tokenCount <= 4) return ranked[0].entry;

    return {
      ...chatbotFallback,
      reply: nextFallbackReply(),
    };
  };

  const deliverSupportReply = (payload) => {
    const typingBubble = addTypingIndicator();
    window.setTimeout(() => {
      typingBubble?.remove();
      addChatMessage(payload.reply || chatbotFallback.reply || "Ask me anything about NDGA.", "agent");
      addQuickReplies(suggestionQuickReplies(payload));
      chatbotInput?.focus();
    }, 260);
  };

  const openMessagesView = () => {
    openChatbot("messages");
    ensureChatIntro();
  };

  const startAdmissionsConversation = () => {
    openMessagesView();
    contactFlow = { active: true, step: "name", data: {} };
    addChatMessage("I can help you send this directly to the school. What is your full name?", "agent");
    chatbotInput?.focus();
  };

  const submitAdmissionsLead = async () => {
    setChatStatus("Creating your ticket...");
    const typingBubble = addTypingIndicator();
    const payload = new FormData();
    payload.append("contact_name", contactFlow.data.contact_name || "");
    payload.append("contact_email", contactFlow.data.contact_email || "");
    payload.append("contact_phone", contactFlow.data.contact_phone || "");
    payload.append("message", contactFlow.data.message || "");

    try {
      const response = await fetch(chatbotLiveChatUrl, {
        method: "POST",
        body: payload,
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": chatbotCsrfToken,
        },
      });
      const data = await response.json();
      typingBubble?.remove();
      if (!response.ok || !data.ok) {
        addChatMessage(
          "I could not create that ticket right now. Please try again here, use the contact page, or send a WhatsApp message.",
          "agent"
        );
        addQuickReplies([
          { label: "Talk to School", action: "lead" },
          { label: "Contact Page", url: "/contact/" },
          { label: "WhatsApp", url: supportWhatsappLink?.href || "/contact/" },
        ]);
        setChatStatus("Ticket not created yet.");
        return;
      }

      addChatMessage(
        data.ticket_reference
          ? `Ticket created. Reference: ${data.ticket_reference}. A confirmation email has been sent to you and the school has received your message.`
          : data.message || "Ticket created and the school has received your message.",
        "agent"
      );
      addQuickReplies(baseQuickReplies());
      setChatStatus("Ticket created.");
      contactFlow = { active: false, step: null, data: {} };
    } catch (error) {
      typingBubble?.remove();
      addChatMessage(
        "I could not complete that request right now. Please try again or use the contact page.",
        "agent"
      );
      addQuickReplies([
        { label: "Talk to School", action: "lead" },
        { label: "Contact Page", url: "/contact/" },
        { label: "WhatsApp", url: supportWhatsappLink?.href || "/contact/" },
      ]);
      setChatStatus("Network error while creating ticket.");
    }
  };

  const advanceAdmissionsConversation = async (text) => {
    if (!contactFlow.active) return false;

    if (contactFlow.step === "name") {
      if (text.trim().length < 2) {
        addChatMessage("Please enter your full name so admissions can identify your enquiry.", "agent");
        return true;
      }
      contactFlow.data.contact_name = text.trim();
      contactFlow.step = "email";
      addChatMessage("Thank you. What email address should admissions reply to?", "agent");
      return true;
    }

    if (contactFlow.step === "email") {
      if (!emailPattern.test(text.trim())) {
        addChatMessage("Please enter a valid email address.", "agent");
        return true;
      }
      contactFlow.data.contact_email = text.trim();
      contactFlow.step = "phone";
      addChatMessage("What phone number should the school use? You can type skip if you prefer not to add one.", "agent");
      return true;
    }

    if (contactFlow.step === "phone") {
      contactFlow.data.contact_phone = /^skip$/i.test(text.trim()) ? "" : text.trim();
      contactFlow.step = "message";
      addChatMessage("Please type your message. You can send an enquiry, complaint, or support request.", "agent");
      return true;
    }

    if (contactFlow.step === "message") {
      if (text.trim().length < 6) {
        addChatMessage("Please add a little more detail so the school can help you properly.", "agent");
        return true;
      }
      contactFlow.data.message = text.trim();
      contactFlow.step = "sending";
      await submitAdmissionsLead();
      return true;
    }

    return false;
  };

  const handleChatQuestion = async (text) => {
    if (!text) return;
    openMessagesView();
    addChatMessage(text, "user");
    if (await advanceAdmissionsConversation(text)) {
      chatbotInput?.focus();
      return;
    }
    const payload = resolveSupportReply(text);
    if (payload.human) {
      startAdmissionsConversation();
      return;
    }
    deliverSupportReply(payload);
  };

  chatToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (chatbot?.classList.contains("is-open")) {
        closeChatbot();
        return;
      }
      openChatbot("home");
    });
  });

  chatbotOpenMessageButtons.forEach((button) => {
    button.addEventListener("click", openMessagesView);
  });

  chatbotHomeActionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.getAttribute("data-chatbot-home-action");
      if (action === "lead") {
        startAdmissionsConversation();
        return;
      }
      openMessagesView();
      chatbotInput?.focus();
    });
  });

  chatbotHomeLinkButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const href = button.getAttribute("data-chatbot-home-link");
      if (href) window.location.href = href;
    });
  });

  chatbotNavButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.getAttribute("data-chatbot-nav") === "messages") {
        openMessagesView();
        return;
      }
      openChatbot("home");
    });
  });

  chatbotBackButtons.forEach((button) => {
    button.addEventListener("click", () => {
      openChatbot("home");
    });
  });

  chatbotCloseButtons.forEach((button) => {
    button.addEventListener("click", closeChatbot);
  });

  chatbotLog?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chatbot-action]");
    if (!button) return;
    const action = button.getAttribute("data-chatbot-action");
    const value = button.getAttribute("data-chatbot-value") || "";

    if (action === "focus") {
      openMessagesView();
      chatbotInput?.focus();
      return;
    }

    if (action === "lead") {
      startAdmissionsConversation();
      return;
    }

    if (action === "query" && value) {
      handleChatQuestion(value);
    }
  });

  chatbotForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = chatbotInput?.value.trim();
    if (!text) return;
    chatbotInput.value = "";
    await handleChatQuestion(text);
  });

  const chatbotMode = new URLSearchParams(window.location.search).get("chatbot");
  if (chatbotMode === "home") {
    openChatbot("home");
  } else if (chatbotMode === "messages") {
    openMessagesView();
  }

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

  rotatingGalleries.forEach((gallery) => {
    const images = [...gallery.querySelectorAll("img")];
    if (images.length < 2) return;
    let index = 0;
    window.setInterval(() => {
      images[index].classList.remove("is-active");
      index = (index + 1) % images.length;
      images[index].classList.add("is-active");
    }, 3200);
  });

  const form = document.querySelector("[data-multi-step-form]");
  if (form) {
    const steps = [...form.querySelectorAll("[data-form-step]")];
    const nextButton = form.querySelector("[data-step-next]");
    const backButton = form.querySelector("[data-step-back]");
    const submitButton = form.querySelector("[data-step-submit]");
    const progressBar = document.querySelector("[data-registration-progress]");
    const indicators = [...document.querySelectorAll("[data-step-indicator]")];
    let stepIndex = 0;
    const currentStepFields = () =>
      [...steps[stepIndex].querySelectorAll("input, select, textarea")]
        .filter((field) => !field.disabled && field.type !== "hidden");
    const stepIsValid = () => {
      let valid = true;
      currentStepFields().forEach((field) => {
        if (!field.checkValidity()) {
          if (valid) field.reportValidity();
          valid = false;
        }
      });
      return valid;
    };
    const updateSteps = () => {
      steps.forEach((step, index) => step.classList.toggle("is-active", index === stepIndex));
      indicators.forEach((step, index) => step.classList.toggle("is-active", index === stepIndex));
      if (progressBar) {
        const width = `${((stepIndex + 1) / Math.max(steps.length, 1)) * 100}%`;
        progressBar.style.width = width;
      }
      if (backButton) backButton.hidden = stepIndex === 0;
      if (nextButton) nextButton.hidden = stepIndex === steps.length - 1;
      if (submitButton) submitButton.hidden = stepIndex !== steps.length - 1;
    };
    nextButton?.addEventListener("click", () => {
      if (!stepIsValid()) return;
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
    form.addEventListener("submit", (event) => {
      if (!stepIsValid()) {
        event.preventDefault();
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

  window.addEventListener("popstate", () => {
    closeChatbot();
    closeSearch();
    closeDrawer();
    closeLightbox();
  });

  document.addEventListener("mousedown", (event) => {
    if (!chatbot?.classList.contains("is-open")) return;
    const clickedToggle = chatToggleButtons.some((button) => button.contains(event.target));
    if (clickedToggle) return;
    if (!chatbot.contains(event.target)) {
      closeChatbot();
    }
  });
})();
