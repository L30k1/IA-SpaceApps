(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const speechSynthesis = window.speechSynthesis;
  const localVoiceAvailable = Boolean(speechSynthesis && window.SpeechSynthesisUtterance);
  let useCloud = false;
  let lastAudio;

  class ErrorAudio extends Error {}

  async function fetchAudio(url, csrf, channel, message_text, signal) {
    const requestController = new AbortController();
    const cancelRequest = () => requestController.abort();
    signal.addEventListener('abort', cancelRequest, { once: true });
    const elapsedMs = setTimeout(cancelRequest, 12000);
    try {
      const reply = await fetch(url, {
        method: 'POST',
        body: new URLSearchParams({ csrf, canal: channel, texto: message_text, usar_nube: '1' }),
        signal: requestController.signal,
      });
      if (!reply.ok) {
        const data = await reply.json().catch(() => null);
        if (typeof data?.error === 'string') throw new ErrorAudio(data.error);
        throw new ErrorAudio(t("Could not retrieve the audio from ElevenLabs."));
      }
      if (!reply.headers.get('Content-Type')?.startsWith('audio/mpeg')) throw new ErrorAudio(t("Could not retrieve the audio from ElevenLabs."));
      const audio = await reply.blob();
      if (!audio.size) throw new ErrorAudio(t("Could not retrieve the audio from ElevenLabs."));
      lastAudio = { texto: message_text, canal: channel, audio };
      return audio;
    } finally {
      clearTimeout(elapsedMs);
      signal.removeEventListener('abort', cancelRequest);
    }
  }

  function create(panel, channel) {
    const providerOption = panel.querySelector('[data-voz-elevenlabs]');
    const diagnostic = panel.querySelector('[data-voz-diagnostico]');
    if (providerOption) {
      providerOption.checked = useCloud;
      providerOption.addEventListener('change', () => { useCloud = providerOption.checked; });
    }
    let playback;

    function stop() {
      const ongoing = playback;
      playback = null;
      ongoing?.abort();
    }

    function play(message_text, onFinished) {
      stop();
      if (diagnostic) diagnostic.textContent = '';
      const turn = new AbortController();
      const { signal } = turn;
      playback = turn;
      function end(success) {
        if (playback !== turn) return;
        stop();
        onFinished(success);
      }

      function playLocalVoice() {
        if (signal.aborted) return;
        if (!localVoiceAvailable) {
          end(false);
          return;
        }
        const utterance = new window.SpeechSynthesisUtterance(message_text);
        utterance.lang = locale;
        const voices = speechSynthesis.getVoices().filter(voice => voice.localService && voice.lang.split('-')[0].toLowerCase() === locale.split('-')[0]);
        const voice = voices.find(option => option.lang.toLowerCase() === locale.toLowerCase()) || voices[0];
        if (voice) utterance.voice = voice;
        utterance.onend = () => end(true);
        utterance.onerror = () => end(false);
        signal.addEventListener('abort', () => speechSynthesis.cancel(), { once: true });
        try {
          speechSynthesis.speak(utterance);
        } catch {
          end(false);
        }
      }

      function fallback(message) {
        diagnostic.textContent = localVoiceAvailable ? message + ' ' + t("The browser voice will be used.") : message;
        playLocalVoice();
      }

      async function playCloudVoice() {
        try {
          const csrf = panel.closest('form').elements.csrf.value;
          const stored = lastAudio?.texto === message_text && lastAudio.canal === channel ? lastAudio.audio : null;
          const data = stored ?? await fetchAudio(providerOption.dataset.vozElevenlabs, csrf, channel, message_text, signal);
          if (signal.aborted) return;
          const audio = new Audio();
          const url = URL.createObjectURL(data);
          audio.src = url;
          let urlActive = true;
          function releaseAudio() {
            audio.pause();
            URL.revokeObjectURL(url);
          }
          signal.addEventListener('abort', releaseAudio, { once: true });
          audio.addEventListener('ended', () => end(true), { once: true, signal });
          audio.addEventListener('error', useFallback, { once: true, signal });
          try {
            await audio.play();
          } catch (error) {
            if (signal.aborted || !urlActive) return;
            if (error.name === 'NotAllowedError') {
              diagnostic.textContent = t("The browser blocked autoplay. Select Play latest reply.");
              end(false);
            } else {
              useFallback();
            }
          }
          function useFallback() {
            if (signal.aborted || !urlActive) return;
            urlActive = false;
            audio.removeEventListener('error', useFallback);
            signal.removeEventListener('abort', releaseAudio);
            releaseAudio();
            fallback(t("The browser could not play the ElevenLabs audio."));
          }
        } catch (error) {
          if (signal.aborted) return;
          fallback(error instanceof ErrorAudio ? error.message : t("Could not retrieve the audio from ElevenLabs."));
        }
      }

      if (providerOption?.checked) playCloudVoice();
      else playLocalVoice();
    }
    return {
      available: localVoiceAvailable || Boolean(providerOption),
      get playing() { return Boolean(playback); },
      get cloudSelected() { return Boolean(providerOption?.checked); },
      stop,
      play,
    };
  }

  window.createAiAudio = create;
})();
