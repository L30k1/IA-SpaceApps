(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const sintesis = window.speechSynthesis;
  const vozLocal = Boolean(sintesis && window.SpeechSynthesisUtterance);
  let usarNube = false;
  let ultimoAudio;

  class ErrorAudio extends Error {}

  async function obtenerAudio(url, csrf, canal, texto, signal) {
    const peticion = new AbortController();
    const cancelar = () => peticion.abort();
    signal.addEventListener('abort', cancelar, { once: true });
    const tiempo = setTimeout(cancelar, 12000);
    try {
      const respuesta = await fetch(url, {
        method: 'POST',
        body: new URLSearchParams({ csrf, canal, texto, usar_nube: '1' }),
        signal: peticion.signal,
      });
      if (!respuesta.ok) {
        const datos = await respuesta.json().catch(() => null);
        if (typeof datos?.error === 'string') throw new ErrorAudio(datos.error);
        throw new ErrorAudio(t('No se pudo obtener el audio de ElevenLabs.'));
      }
      if (!respuesta.headers.get('Content-Type')?.startsWith('audio/mpeg')) throw new ErrorAudio(t('No se pudo obtener el audio de ElevenLabs.'));
      const audio = await respuesta.blob();
      if (!audio.size) throw new ErrorAudio(t('No se pudo obtener el audio de ElevenLabs.'));
      ultimoAudio = { texto, canal, audio };
      return audio;
    } finally {
      clearTimeout(tiempo);
      signal.removeEventListener('abort', cancelar);
    }
  }

  function crear(panel, canal) {
    const eleccion = panel.querySelector('[data-voz-elevenlabs]');
    const diagnostico = panel.querySelector('[data-voz-diagnostico]');
    if (eleccion) {
      eleccion.checked = usarNube;
      eleccion.addEventListener('change', () => { usarNube = eleccion.checked; });
    }
    let lectura;

    function detener() {
      const enCurso = lectura;
      lectura = null;
      enCurso?.abort();
    }

    function leer(texto, terminado) {
      detener();
      if (diagnostico) diagnostico.textContent = '';
      const turno = new AbortController();
      const { signal } = turno;
      lectura = turno;
      function fin(exito) {
        if (lectura !== turno) return;
        detener();
        terminado(exito);
      }

      function hablarLocal() {
        if (signal.aborted) return;
        if (!vozLocal) {
          fin(false);
          return;
        }
        const frase = new window.SpeechSynthesisUtterance(texto);
        frase.lang = locale;
        const voces = sintesis.getVoices().filter(voz => voz.localService && voz.lang.split('-')[0].toLowerCase() === locale.split('-')[0]);
        const voz = voces.find(opcion => opcion.lang.toLowerCase() === locale.toLowerCase()) || voces[0];
        if (voz) frase.voice = voz;
        frase.onend = () => fin(true);
        frase.onerror = () => fin(false);
        signal.addEventListener('abort', () => sintesis.cancel(), { once: true });
        try {
          sintesis.speak(frase);
        } catch {
          fin(false);
        }
      }

      function respaldar(mensaje) {
        diagnostico.textContent = vozLocal ? mensaje + ' ' + t('Se usará la voz del navegador.') : mensaje;
        hablarLocal();
      }

      async function hablarEnNube() {
        try {
          const csrf = panel.closest('form').elements.csrf.value;
          const guardado = ultimoAudio?.texto === texto && ultimoAudio.canal === canal ? ultimoAudio.audio : null;
          const datos = guardado ?? await obtenerAudio(eleccion.dataset.vozElevenlabs, csrf, canal, texto, signal);
          if (signal.aborted) return;
          const audio = new Audio();
          const url = URL.createObjectURL(datos);
          audio.src = url;
          let urlActiva = true;
          function liberar() {
            audio.pause();
            URL.revokeObjectURL(url);
          }
          signal.addEventListener('abort', liberar, { once: true });
          audio.addEventListener('ended', () => fin(true), { once: true, signal });
          audio.addEventListener('error', usarRespaldo, { once: true, signal });
          try {
            await audio.play();
          } catch (error) {
            if (signal.aborted || !urlActiva) return;
            if (error.name === 'NotAllowedError') {
              diagnostico.textContent = t('El navegador bloqueó la reproducción automática. Pulsa Escuchar última respuesta.');
              fin(false);
            } else {
              usarRespaldo();
            }
          }
          function usarRespaldo() {
            if (signal.aborted || !urlActiva) return;
            urlActiva = false;
            audio.removeEventListener('error', usarRespaldo);
            signal.removeEventListener('abort', liberar);
            liberar();
            respaldar(t('El navegador no pudo reproducir el audio de ElevenLabs.'));
          }
        } catch (error) {
          if (signal.aborted) return;
          respaldar(error instanceof ErrorAudio ? error.message : t('No se pudo obtener el audio de ElevenLabs.'));
        }
      }

      if (eleccion?.checked) hablarEnNube();
      else hablarLocal();
    }
    return {
      disponible: vozLocal || Boolean(eleccion),
      get enCurso() { return Boolean(lectura); },
      get nubeElegida() { return Boolean(eleccion?.checked); },
      detener,
      leer,
    };
  }

  window.crearAudioIA = crear;
})();
