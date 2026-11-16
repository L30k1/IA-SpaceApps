(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const { appendMessage, scrollToLatest } = window.mediSpaceChat;
  const section = document.querySelector('[data-emergencia]');
  const panel = section?.querySelector('[data-voz-emergencia]');
  if (!panel) return;

  const form = panel.closest('form');
  const message = form.elements.mensaje;
  const submitTurn = form.querySelector('[type="submit"]');
  const conversation = section.querySelector('[data-chat-mensajes]');
  const microphone = panel.querySelector('[data-emergencia-mic]');
  const state = panel.querySelector('[data-voz-estado]');
  const playButton = panel.querySelector('[data-voz-escuchar]');
  const player = window.createAiAudio(panel, 'emergencia');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition_round = SpeechRecognition && window.isSecureContext ? new SpeechRecognition() : null;
  const language = locale;
  const errors = {
    'not-allowed': t("Select Turn on microphone and allow access in your browser. You can also type."),
    'service-not-allowed': t("The browser is blocking dictation. You can type your message."),
    'audio-capture': t("A microphone could not be found. You can type your message."),
    network: t("The dictation service is unavailable. You can type your message."),
  };
  let active = false;
  let isCapturing = false;
  let isClosing = false;
  let discarded = false;
  let isSending = false;
  let lastReply = Array.from(conversation.querySelectorAll('[data-voz-respuesta]')).at(-1)?.textContent.trim();
  let pauseTime;
  let shouldRetry;
  let transcript = '';

  function toggleMicrophone(microphoneOn) {
    active = microphoneOn;
    microphone.textContent = microphoneOn ? t("Turn off microphone") : t("Turn on microphone");
    microphone.setAttribute('aria-pressed', String(microphoneOn));
  }

  function discardCapture() {
    clearTimeout(pauseTime);
    clearTimeout(shouldRetry);
    if (isCapturing) {
      discarded = true;
      recognition_round.abort();
    }
  }

  function stopVoice(notice) {
    toggleMicrophone(false);
    discardCapture();
    stopPlayback();
    state.textContent = notice;
  }

  function playReply() {
    if (!active || isCapturing || isSending || player.playing) return;
    transcript = '';
    discarded = false;
    isClosing = false;
    try {
      recognition_round.start();
      isCapturing = true;
      state.textContent = t("Turning on microphone…");
    } catch {
      stopVoice(errors['not-allowed']);
    }
  }

  function finishUtterance() {
    clearTimeout(pauseTime);
    if (!isCapturing || isClosing || discarded) return;
    isClosing = true;
    recognition_round.stop();
  }

  function stopPlayback() {
    player.stop();
    playButton.textContent = t("Play latest reply");
  }

  function playResponse(message_text, manualMode = false) {
    if (!player.available || (!active && !manualMode && !player.cloudSelected)) {
      state.textContent = t("The reply is available in the chat.");
      playReply();
      return;
    }
    discardCapture();
    playButton.textContent = t("Stop playback");
    state.textContent = active
      ? t("The AI is replying. The microphone is paused.")
      : t("Playing the AI reply…");
    player.play(message_text, success => {
      playButton.textContent = t("Play latest reply");
      state.textContent = success ? '' : t("To hear this reply, select Play latest reply.");
      playReply();
    });
  }

  playButton.hidden = !lastReply || !player.available;
  playButton.addEventListener('click', () => {
    if (isSending) return;
    if (player.playing) {
      stopPlayback();
      playReply();
    } else if (lastReply) playResponse(lastReply, true);
  });

  async function sendTurn() {
    if (isSending || !message.value.trim()) return;
    isSending = true;
    discardCapture();
    const data = new FormData(form);
    message.readOnly = true;
    submitTurn.disabled = true;
    state.textContent = t("Sending to the AI…");
    const pendiente = appendMessage(conversation, { role: 'user', text: message.value.trim() }, true);
    let new_turns;
    try {
      const reply = await fetch(form.action, {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: data,
      });
      const resultData = await reply.json();
      if (reply.ok) {
        form.elements.revision.value = resultData.revision;
        message.value = '';
        new_turns = resultData.mensajes;
      } else {
        stopVoice(resultData.error);
      }
    } catch {
      stopVoice(t("Sending could not be confirmed. Keep your message and check the chat before sending it again."));
    } finally {
      pendiente.remove();
      isSending = false;
      message.readOnly = false;
      submitTurn.disabled = false;
    }
    if (new_turns) {
      conversation.querySelector('#ultimo-mensaje')?.removeAttribute('id');
      for (const turn of new_turns) appendMessage(conversation, turn);
      conversation.lastElementChild.id = 'ultimo-mensaje';
      lastReply = new_turns.at(-1).text;
      playButton.hidden = !player.available;
      playResponse(lastReply);
    }
  }
  scrollToLatest(conversation);

  form.addEventListener('submit', event => {
    event.preventDefault();
    stopPlayback();
    sendTurn();
  });
  message.addEventListener('input', () => {
    if (active) stopVoice(t("Microphone off while you type."));
  });

  window.addEventListener('pagehide', () => stopVoice(t("Microphone turned off when leaving the chat.")));
  if (!recognition_round) {
    state.textContent = t("Dictation requires a compatible browser and a secure connection. You can type your message.");
    return;
  }

  recognition_round.lang = language;
  recognition_round.continuous = true;
  recognition_round.interimResults = true;
  recognition_round.onstart = () => {
    if (active && !discarded) state.textContent = t("Microphone on. Speak whenever you are ready.");
  };
  recognition_round.onspeechstart = () => clearTimeout(pauseTime);
  recognition_round.onspeechend = finishUtterance;
  recognition_round.onresult = event => {
    if (discarded) return;
    transcript = Array.from(event.results, resultData => resultData[0].transcript.trim())
      .join(' ').trim().slice(0, message.maxLength);
    if (!transcript) return;
    message.value = transcript;
    clearTimeout(pauseTime);
    if (!isClosing) pauseTime = setTimeout(finishUtterance, 1100);
  };
  recognition_round.onerror = event => {
    if (discarded || event.error === 'no-speech' || event.error === 'aborted') return;
    stopVoice(errors[event.error] || t("Dictation stopped. Turn the microphone back on or type your message."));
  };
  recognition_round.onend = () => {
    isCapturing = false;
    clearTimeout(pauseTime);
    if (!active) return;
    if (transcript && !discarded) sendTurn();
    else shouldRetry = setTimeout(playReply, 300);
  };

  function enableVoice() {
    if (message.value.trim()) {
      state.textContent = t("Send or clear your draft before turning on the microphone.");
      return;
    }
    toggleMicrophone(true);
    playReply();
  }

  microphone.hidden = false;
  microphone.addEventListener('click', () => {
    if (active) stopVoice(t("Microphone off."));
    else enableVoice();
  });
  enableVoice();
})();
