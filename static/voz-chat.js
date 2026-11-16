(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const language = locale;
  const { appendMessage, scrollToLatest } = window.mediSpaceChat;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const responseSelector = '[data-voz-respuesta]';

  function setupChat(section, playOnOpen = false) {
    const panel = section.querySelector('[data-voz-chat]');
    if (!panel) return;
    const form = panel.closest('form');
    const message = form.querySelector('[data-voz-mensaje]');
    const conversation = section.querySelector('[data-chat-mensajes]');
    const answers = section.querySelectorAll(responseSelector);
    const lastReply = answers[answers.length - 1]?.textContent.trim();
    const dictate = panel.querySelector('[data-voz-dictar]');
    const playReply = panel.querySelector('[data-voz-escuchar]');
    const state = panel.querySelector('[data-voz-estado]');
    const player = window.createAiAudio(panel, section.dataset.chatVoz);
    const canPlay = player.available;
    const events = new AbortController();
    const { signal } = events;
    let recognition_round;
    let keypress = null;
    let isTranscribing = false;
    let isSending = false;

    function stopPlayback() {
      player.stop();
      playReply.textContent = t("Play latest reply");
    }

    function playResponse() {
      if (!canPlay || !lastReply || isTranscribing || isSending) return;
      playReply.textContent = t("Stop playback");
      player.play(lastReply, success => {
        playReply.textContent = t("Play latest reply");
        if (!success) state.textContent = t("To hear this reply, select Play latest reply.");
      });
    }

    if (canPlay && lastReply) {
      playReply.hidden = false;
      playReply.addEventListener('click', () => {
        if (player.playing) stopPlayback();
        else playResponse();
      }, { signal });
    }

    function release() {
      if (keypress === null) return;
      keypress = null;
      dictate.setAttribute('aria-pressed', 'false');
      if (isTranscribing) recognition_round.stop();
    }

    if (SpeechRecognition && window.isSecureContext) {
      recognition_round = new SpeechRecognition();
      recognition_round.lang = language;
      recognition_round.continuous = true;
      recognition_round.interimResults = false;
      const errors = {
        'not-allowed': t("Allow microphone access in your browser to speak."),
        'service-not-allowed': t("The browser is blocking the dictation service."),
        'audio-capture': t("An available microphone could not be found."),
        'no-speech': t("No speech was detected. You can try again."),
        'network': t("The dictation service is unavailable. You can type your message."),
      };
      let hasResult;
      let hadError;

      function press(origin) {
        if (isTranscribing || isSending) return;
        stopPlayback();
        hasResult = false;
        hadError = false;
        try {
          recognition_round.start();
          isTranscribing = true;
          keypress = origin;
          dictate.setAttribute('aria-pressed', 'true');
          state.textContent = t("Listening…");
        } catch {
          state.textContent = t("Dictation could not start.");
        }
      }

      recognition_round.onstart = () => {
        if (keypress === null) recognition_round.stop();
      };
      recognition_round.onresult = (event) => {
        const parts = Array.from(event.results).slice(event.resultIndex);
        const transcribedText = parts.filter(piece => piece.isFinal).map(piece => piece[0].transcript.trim()).join(' ').trim();
        if (!transcribedText) return;
        const separator = message.value && !/\s$/.test(message.value) ? ' ' : '';
        const remainingTime = message.maxLength - message.value.length - separator.length;
        const appended = transcribedText.slice(0, Math.max(0, remainingTime)).replace(/[\uD800-\uDBFF]$/, '');
        if (appended) message.value += separator + appended;
        hasResult = true;
        state.textContent = appended.length < transcribedText.length
          ? t("You reached the character limit. Review your message.")
          : t("Review the transcription and select Send.");
      };
      recognition_round.onerror = (event) => {
        hadError = true;
        state.textContent = errors[event.error] || t("The browser could not transcribe the message.");
      };
      recognition_round.onend = () => {
        isTranscribing = false;
        keypress = null;
        dictate.setAttribute('aria-pressed', 'false');
        if (!hasResult && !hadError) state.textContent = t("No speech was detected. You can try again.");
      };

      dictate.hidden = false;
      panel.querySelector('[data-voz-aviso]').hidden = false;
      window.addEventListener('keydown', (event) => {
        if (event.code !== 'Space' || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        if (event.target !== dictate && event.target.closest?.('input, textarea, select, button, a, [contenteditable]')) return;
        event.preventDefault();
        if (!event.repeat) press('teclado');
      }, { signal });
      window.addEventListener('keyup', (event) => {
        if (event.code !== 'Space' || keypress !== 'teclado') return;
        event.preventDefault();
        release();
      }, { signal });
      dictate.addEventListener('pointerdown', (event) => {
        if (event.button !== 0 || !event.isPrimary || isTranscribing || isSending) return;
        dictate.setPointerCapture(event.pointerId);
        press(event.pointerId);
      }, { signal });
      for (const kind of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        dictate.addEventListener(kind, (event) => {
          if (keypress === event.pointerId) release();
        }, { signal });
      }
      window.addEventListener('blur', release, { signal });
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) release();
      }, { signal });
    }

    panel.hidden = false;
    scrollToLatest(conversation);
    if (dictate.hidden && playReply.hidden && !canPlay) {
      state.textContent = t("Voice controls for this chat are unavailable in this browser.");
    }

    form.addEventListener('submit', async (event) => {
      if (isTranscribing || isSending) {
        event.preventDefault();
        if (isTranscribing) state.textContent = t("Release to finish dictation before sending.");
        return;
      }
      if (event.submitter?.value === 'finalizar') return;
      event.preventDefault();
      const data = new FormData(form);
      if (event.submitter?.name) data.set(event.submitter.name, event.submitter.value);
      const usedKeyboard = document.activeElement === message;
      const controls = Array.from(form.querySelectorAll('button[type="submit"]'));
      isSending = true;
      message.readOnly = true;
      for (const button of controls) button.disabled = true;
      stopPlayback();
      const message_text = message.value.trim();
      const pendiente = message_text ? appendMessage(conversation, { role: 'user', text: message_text }, true) : null;
      state.textContent = t("Waiting for the AI to reply…");
      try {
        const reply = await fetch(form.action, {
          method: 'POST', body: data, headers: { 'X-MediSpace-Chat': '1' }, signal,
        });
        const page_number = new DOMParser().parseFromString(await reply.text(), 'text/html');
        const refreshedForm = page_number.querySelector('[data-chat-voz]');
        if (refreshedForm?.dataset.chatVoz === section.dataset.chatVoz) {
          const newReply = refreshedForm.querySelectorAll(responseSelector).length > answers.length;
          events.abort();
          section.replaceWith(refreshedForm);
          setupChat(refreshedForm, newReply);
          const destination = refreshedForm.querySelector(usedKeyboard ? '[data-voz-mensaje]' : '[data-voz-dictar]:not([hidden])');
          destination?.focus({ preventScroll: true });
        } else if (reply.redirected) {
          window.location.assign(reply.url);
        } else {
          state.textContent = t("Sending could not be confirmed. Check the conversation before trying again.");
        }
      } catch (error) {
        if (error.name !== 'AbortError') state.textContent = t("Sending could not be confirmed. Check the conversation before trying again.");
      } finally {
        pendiente?.remove();
        isSending = false;
        message.readOnly = false;
        for (const button of controls) button.disabled = false;
      }
    }, { signal });

    window.addEventListener('pagehide', () => {
      release();
      stopPlayback();
    }, { signal });
    if (playOnOpen) {
      if (document.hidden) document.addEventListener('visibilitychange', playResponse, { once: true, signal });
      else playResponse();
    }
  }

  const section = document.querySelector('[data-chat-voz]');
  if (section) setupChat(section, section.hasAttribute('data-voz-inicial'));
})();
