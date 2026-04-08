(() => {
  const body = document.body;
  const header = document.querySelector("[data-public-header]");
  const drawer = document.querySelector("[data-mobile-drawer]");
  const backdrop = document.querySelector("[data-mobile-backdrop]");
  const searchModal = document.querySelector("[data-search-modal]");
  const searchInput = document.querySelector("[data-search-input]");
  const searchItems = [...document.querySelectorAll("[data-search-item]")];
  const chatbot = document.querySelector("[data-chatbot]");
  const chatToggleButtons = [...document.querySelectorAll("[data-chatbot-open]")];
  const supportViews = [...document.querySelectorAll("[data-support-view]")];
  const supportTabs = [...document.querySelectorAll("[data-support-tab]")];
  const chatbotLog = document.querySelector("[data-chatbot-log]");
  const chatbotForm = document.querySelector("[data-chatbot-form]");
  const chatbotInput = chatbotForm?.querySelector("input");
  const chatbotEscalation = document.querySelector("[data-chatbot-escalation]");
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImage = document.querySelector("[data-lightbox-target]");
  const lightboxCaption = document.querySelector("[data-lightbox-caption]");
  const liveChatShell = document.querySelector("[data-live-chat-shell]");
  const liveChatForm = document.querySelector("[data-live-chat-form]");
  const liveChatStatus = document.querySelector("[data-live-chat-status]");
  const supportTicketList = document.querySelector("[data-support-ticket-list]");
  const rotatingGalleries = [...document.querySelectorAll("[data-rotating-gallery]")];

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

  const setSupportView = (target) => {
    if (!target) return;
    supportViews.forEach((view) => {
      view.classList.toggle("is-active", view.getAttribute("data-support-view") === target);
    });
    supportTabs.forEach((tab) => {
      tab.classList.toggle("is-active", tab.getAttribute("data-support-tab") === target);
    });
  };

  const openChatbot = (targetView = "home") => {
    if (!chatbot) return;
    chatbot?.classList.add("is-open");
    setSupportView(targetView);
  };
  const closeChatbot = () => {
    chatbot?.classList.remove("is-open");
    setSupportView("home");
    toggleEscalationPrompt(false);
    if (liveChatShell) {
      liveChatShell.hidden = true;
    }
    if (liveChatStatus) {
      liveChatStatus.textContent = "";
    }
  };

  const addChatMessage = (text, sender, options = {}) => {
    if (!chatbotLog || !text) return;
    const article = document.createElement("article");
    article.className = `public-live-chat-bubble is-${sender}`;
    const title = document.createElement("strong");
    title.textContent = options.label || (sender === "user" ? "Visitor" : "Smart Julie");
    const body = document.createElement("p");
    body.textContent = text;
    article.append(title, body);
    chatbotLog.appendChild(article);
    chatbotLog.scrollTop = chatbotLog.scrollHeight;
  };

  const toggleEscalationPrompt = (visible) => {
    if (!chatbotEscalation) return;
    chatbotEscalation.hidden = !visible;
  };

  const supportKnowledge = [
    {
      matches: ["apply", "application", "admission", "register", "registration", "form"],
      reply:
        "Begin from the online registration page. Applicants provide student details, boarding preference, and supporting documents before screening and approval.",
    },
    {
      matches: ["exam", "screening", "screen", "entrance"],
      reply:
        "Entrance screening covers English Language, Mathematics, and General Paper. The admissions team confirms each screening date after registration review.",
    },
    {
      matches: ["boarding", "hostel", "boarder"],
      reply:
        "NDGA is a boarding school with supervised hostel routine, prep, welfare guidance, and structured daily care for students.",
    },
    {
      matches: ["fee", "fees", "payment", "pay", "bursar"],
      reply:
        "The fees page shows the class-by-class structure, while management and bursary guidance confirm the latest approved figures for each admission cycle.",
    },
    {
      matches: ["subject", "curriculum", "academic", "waec", "neco", "class", "jss", "ss"],
      reply:
        "NDGA offers junior and senior secondary learning with core subjects, exam preparation, ICT exposure, and structured academic follow-up across the term.",
    },
    {
      matches: ["club", "sports", "music", "jets", "activities", "co-curricular"],
      reply:
        "Student life includes clubs, sports, leadership opportunities, faith formation, and school activities that support balanced development.",
    },
    {
      matches: ["location", "map", "direction", "address", "where"],
      reply:
        "The school is just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje-Abuja. Use the map link in this panel for direct navigation.",
    },
    {
      matches: ["contact", "email", "phone", "office"],
      reply:
        "You can reach the school through +234 902 940 5413, +234 813 341 3127, or office@ndgakuje.org.",
    },
    {
      matches: ["principal", "welcome", "hallmark", "history", "sisters", "catholic"],
      reply:
        "NDGA is a Catholic girls' secondary school of the Sisters of Notre Dame de Namur, shaped by learning, discipline, community, service, and faith formation.",
    },
    {
      matches: ["term", "resumption", "resume", "calendar"],
      reply:
        "Third term for the 2025/2026 session is set to begin on April 20, 2026. Earlier term records remain viewable through portal filters.",
    },
    {
      matches: ["portal", "result", "download", "performance"],
      reply:
        "Students and parents can use the portal to view results, download reports, check finance visibility, and follow approved school updates.",
    },
  ];

  const resolveSupportReply = (message) => {
    const text = message.toLowerCase();
    const directEscalation =
      text.includes("management") ||
      text.includes("human") ||
      text.includes("agent") ||
      text.includes("live chat");
    if (directEscalation) {
      return {
        reply: "I can connect you with management. Would you like me to open the management chat queue?",
        escalate: true,
      };
    }
    const match = supportKnowledge.find((entry) =>
      entry.matches.some((token) => text.includes(token))
    );
    if (match) {
      return { reply: match.reply, escalate: false };
    }
    return {
      reply:
        "I may not have the exact answer to that yet. Would you like to chat with management so your enquiry can be handled directly?",
      escalate: true,
    };
  };

  chatToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (chatbot?.classList.contains("is-open")) {
        closeChatbot();
        return;
      }
      openChatbot(button.getAttribute("data-support-target") || "home");
    });
  });
  document.querySelector("[data-chatbot-close]")?.addEventListener("click", closeChatbot);
  supportTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      openChatbot(tab.getAttribute("data-support-tab"));
    });
  });
  document.querySelector("[data-support-open-messages]")?.addEventListener("click", () => {
    openChatbot("messages");
    chatbotInput?.focus();
  });

  const handleChatQuestion = (text) => {
    if (!text) return;
    openChatbot("messages");
    addChatMessage(text, "user");
    const payload = resolveSupportReply(text);
    addChatMessage(payload.reply, "agent");
    toggleEscalationPrompt(payload.escalate);
    if (!payload.escalate) {
      window.setTimeout(() => chatbotInput?.focus(), 120);
    }
  };

  document.querySelectorAll("[data-chatbot-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      handleChatQuestion(chip.getAttribute("data-chatbot-chip") || "");
    });
  });
  chatbotForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = chatbotInput?.value.trim();
    if (!text) return;
    handleChatQuestion(text);
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

  const LIVE_CHAT_STORAGE_KEY = "ndga_public_live_chat_messages";
  const TICKET_STORAGE_KEY = "ndga_public_live_chat_tickets";

  const appendLiveChatBubble = (text, sender, label) => {
    addChatMessage(text, sender, { label: label || (sender === "user" ? "Visitor" : "Management") });
  };

  const saveLiveChatMessages = () => {
    if (!chatbotLog || !window.sessionStorage) return;
    const payload = [...chatbotLog.querySelectorAll(".public-live-chat-bubble")].slice(1).map((item) => ({
      sender: item.classList.contains("is-user") ? "user" : "agent",
      label: item.querySelector("strong")?.textContent || "",
      text: item.querySelector("p")?.textContent || "",
    }));
    window.sessionStorage.setItem(LIVE_CHAT_STORAGE_KEY, JSON.stringify(payload));
  };

  const loadLiveChatMessages = () => {
    if (!chatbotLog || !window.sessionStorage) return;
    try {
      const raw = window.sessionStorage.getItem(LIVE_CHAT_STORAGE_KEY);
      if (!raw) return;
      const messages = JSON.parse(raw);
      messages.forEach((message) => appendLiveChatBubble(message.text, message.sender, message.label));
    } catch (error) {
      window.sessionStorage.removeItem(LIVE_CHAT_STORAGE_KEY);
    }
  };

  const renderTickets = () => {
    if (!supportTicketList || !window.sessionStorage) return;
    const raw = window.sessionStorage.getItem(TICKET_STORAGE_KEY);
    const tickets = raw ? JSON.parse(raw) : [];
    if (!tickets.length) {
      supportTicketList.innerHTML =
        '<article class="ndga-support-ticket-card is-empty"><strong>No open tickets yet</strong><p>When a management request is submitted, the reference and status will appear here during your visit.</p></article>';
      return;
    }
    supportTicketList.innerHTML = "";
    tickets.forEach((ticket) => {
      const card = document.createElement("article");
      card.className = "ndga-support-ticket-card";
      card.innerHTML = `<strong>${ticket.reference}</strong><p>${ticket.summary}</p><small>${ticket.status}</small>`;
      supportTicketList.appendChild(card);
    });
  };

  const pushTicket = (reference, summary) => {
    if (!window.sessionStorage) return;
    const raw = window.sessionStorage.getItem(TICKET_STORAGE_KEY);
    const tickets = raw ? JSON.parse(raw) : [];
    tickets.unshift({
      reference,
      summary,
      status: "Awaiting management reply",
    });
    window.sessionStorage.setItem(TICKET_STORAGE_KEY, JSON.stringify(tickets.slice(0, 5)));
    renderTickets();
  };

  const connectToManagement = () => {
    const waitText =
      chatbot?.getAttribute("data-chat-management-wait") ||
      "Connecting you to management. Please wait...";
    toggleEscalationPrompt(false);
    openChatbot("messages");
    appendLiveChatBubble(waitText, "agent", "System");
    if (liveChatShell) {
      liveChatShell.hidden = false;
    }
    window.setTimeout(() => {
      appendLiveChatBubble(
        "If the Vice Principal or IT Manager is not immediately available, your message will be saved as a ticket and the reply will be sent to your email.",
        "agent",
        "Management Queue"
      );
      liveChatForm?.querySelector("input[name='contact_email']")?.focus();
      saveLiveChatMessages();
    }, 1400);
  };

  loadLiveChatMessages();
  renderTickets();

  document.querySelectorAll("[data-chatbot-escalate]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.getAttribute("data-chatbot-escalate") === "yes") {
        connectToManagement();
        return;
      }
      toggleEscalationPrompt(false);
      appendLiveChatBubble("No problem. You can continue here and I will keep helping.", "agent");
      saveLiveChatMessages();
    });
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

  liveChatForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!liveChatForm || !liveChatStatus) return;
    const emailInput = liveChatForm.querySelector("input[name='contact_email']");
    const messageInput = liveChatForm.querySelector("textarea[name='message']");
    const emailValue = emailInput?.value.trim();
    const messageText = messageInput?.value.trim();
    if (!emailValue) {
      liveChatStatus.textContent = "Email address is required so management can reply to you.";
      emailInput?.focus();
      return;
    }
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
        liveChatStatus.textContent =
          payload.errors?.contact_email?.[0]?.message || "Please complete the required fields and try again.";
        if (chatbotLog) {
          const bubbles = chatbotLog.querySelectorAll(".public-live-chat-bubble.is-user");
          bubbles[bubbles.length - 1]?.remove();
          saveLiveChatMessages();
        }
        return;
      }
      liveChatForm.reset();
      appendLiveChatBubble(
        payload.message || "Your message has been sent to management.",
        "agent",
        "Management Queue"
      );
      if (payload.ticket_reference) {
        pushTicket(payload.ticket_reference, messageText || "Management enquiry");
      }
      saveLiveChatMessages();
      liveChatStatus.textContent = payload.ticket_reference
        ? `Ticket ${payload.ticket_reference} created. Replies will be sent to your email.`
        : payload.message || "Your message has been sent.";
    } catch (error) {
      liveChatStatus.textContent = "Unable to send right now. Please try again.";
      if (chatbotLog) {
        const bubbles = chatbotLog.querySelectorAll(".public-live-chat-bubble.is-user");
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
    }
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
