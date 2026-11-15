(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const idioma = locale;
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const sintesis = window.speechSynthesis;
  const puedeLeer = Boolean(sintesis && window.SpeechSynthesisUtterance);
  const selectorRespuestas = '[data-voz-respuesta]';

  function prepararChat(seccion, leerAlAbrir = false) {
    const panel = seccion.querySelector('[data-voz-chat]');
    if (!panel) return;
    const form = panel.closest('form');
    const mensaje = form.querySelector('[data-voz-mensaje]');
    const respuestas = seccion.querySelectorAll(selectorRespuestas);
    const ultima = respuestas[respuestas.length - 1]?.textContent.trim();
    const dictar = panel.querySelector('[data-voz-dictar]');
    const escuchar = panel.querySelector('[data-voz-escuchar]');
    const estado = panel.querySelector('[data-voz-estado]');
    const eventos = new AbortController();
    const { signal } = eventos;
    let fraseActiva = null;
    let reconocimiento;
    let pulsacion = null;
    let transcribiendo = false;
    let enviando = false;

    function detenerLectura() {
      if (fraseActiva) {
        fraseActiva = null;
        sintesis.cancel();
      }
      escuchar.textContent = t('Escuchar última respuesta');
    }

    function leerRespuesta() {
      if (!puedeLeer || !ultima || transcribiendo || enviando) return;
      detenerLectura();
      const frase = new window.SpeechSynthesisUtterance(ultima);
      frase.lang = idioma;
      const voces = sintesis.getVoices().filter(voz => voz.localService && voz.lang.split('-')[0].toLowerCase() === idioma.split('-')[0]);
      const voz = voces.find(opcion => opcion.lang.toLowerCase() === idioma.toLowerCase()) || voces[0];
      if (voz) frase.voice = voz;
      frase.onend = () => {
        if (fraseActiva !== frase) return;
        fraseActiva = null;
        escuchar.textContent = t('Escuchar última respuesta');
      };
      frase.onerror = () => {
        if (fraseActiva !== frase) return;
        detenerLectura();
        estado.textContent = t('Para oír esta respuesta, pulsa Escuchar última respuesta.');
      };
      fraseActiva = frase;
      escuchar.textContent = t('Detener lectura');
      sintesis.speak(frase);
    }

    if (puedeLeer && ultima) {
      escuchar.hidden = false;
      escuchar.addEventListener('click', () => {
        if (fraseActiva) detenerLectura();
        else leerRespuesta();
      }, { signal });
    }

    function soltar() {
      if (pulsacion === null) return;
      pulsacion = null;
      dictar.setAttribute('aria-pressed', 'false');
      if (transcribiendo) reconocimiento.stop();
    }

    if (Reconocimiento && window.isSecureContext) {
      reconocimiento = new Reconocimiento();
      reconocimiento.lang = idioma;
      reconocimiento.continuous = true;
      reconocimiento.interimResults = false;
      const errores = {
        'not-allowed': t('Autoriza el micrófono en el navegador para hablar.'),
        'service-not-allowed': t('El navegador no permite el servicio de dictado.'),
        'audio-capture': t('No se encontró un micrófono disponible.'),
        'no-speech': t('No se detectó voz. Puedes intentar de nuevo.'),
        'network': t('El servicio de dictado no está disponible. Puedes escribir tu mensaje.'),
      };
      let hayResultado;
      let huboError;

      function pulsar(origen) {
        if (transcribiendo || enviando) return;
        detenerLectura();
        hayResultado = false;
        huboError = false;
        try {
          reconocimiento.start();
          transcribiendo = true;
          pulsacion = origen;
          dictar.setAttribute('aria-pressed', 'true');
          estado.textContent = t('Escuchando…');
        } catch {
          estado.textContent = t('No se pudo iniciar el dictado.');
        }
      }

      reconocimiento.onstart = () => {
        if (pulsacion === null) reconocimiento.stop();
      };
      reconocimiento.onresult = (evento) => {
        const partes = Array.from(evento.results).slice(evento.resultIndex);
        const transcrito = partes.filter(parte => parte.isFinal).map(parte => parte[0].transcript.trim()).join(' ').trim();
        if (!transcrito) return;
        const separador = mensaje.value && !/\s$/.test(mensaje.value) ? ' ' : '';
        const restante = mensaje.maxLength - mensaje.value.length - separador.length;
        const agregado = transcrito.slice(0, Math.max(0, restante)).replace(/[\uD800-\uDBFF]$/, '');
        if (agregado) mensaje.value += separador + agregado;
        hayResultado = true;
        estado.textContent = agregado.length < transcrito.length
          ? t('Se alcanzó el límite de caracteres. Revisa el mensaje.')
          : t('Revisa el dictado y pulsa Enviar.');
      };
      reconocimiento.onerror = (evento) => {
        huboError = true;
        estado.textContent = errores[evento.error] || t('El navegador no pudo transcribir el mensaje.');
      };
      reconocimiento.onend = () => {
        transcribiendo = false;
        pulsacion = null;
        dictar.setAttribute('aria-pressed', 'false');
        if (!hayResultado && !huboError) estado.textContent = t('No se detectó voz. Puedes intentar de nuevo.');
      };

      dictar.hidden = false;
      panel.querySelector('[data-voz-aviso]').hidden = false;
      window.addEventListener('keydown', (evento) => {
        if (evento.code !== 'Space' || evento.altKey || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
        if (evento.target !== dictar && evento.target.closest?.('input, textarea, select, button, a, [contenteditable]')) return;
        evento.preventDefault();
        if (!evento.repeat) pulsar('teclado');
      }, { signal });
      window.addEventListener('keyup', (evento) => {
        if (evento.code !== 'Space' || pulsacion !== 'teclado') return;
        evento.preventDefault();
        soltar();
      }, { signal });
      dictar.addEventListener('pointerdown', (evento) => {
        if (evento.button !== 0 || !evento.isPrimary || transcribiendo || enviando) return;
        dictar.setPointerCapture(evento.pointerId);
        pulsar(evento.pointerId);
      }, { signal });
      for (const tipo of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        dictar.addEventListener(tipo, (evento) => {
          if (pulsacion === evento.pointerId) soltar();
        }, { signal });
      }
      window.addEventListener('blur', soltar, { signal });
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) soltar();
      }, { signal });
    }

    panel.hidden = false;
    if (dictar.hidden && escuchar.hidden && !puedeLeer) {
      estado.textContent = t('Este navegador no tiene controles de voz disponibles para este chat.');
    }

    form.addEventListener('submit', async (evento) => {
      if (transcribiendo || enviando) {
        evento.preventDefault();
        if (transcribiendo) estado.textContent = t('Suelta para terminar el dictado antes de enviar.');
        return;
      }
      if (!puedeLeer || evento.submitter?.value === 'finalizar') return;
      evento.preventDefault();
      const datos = new FormData(form);
      if (evento.submitter?.name) datos.set(evento.submitter.name, evento.submitter.value);
      const fueTeclado = document.activeElement === mensaje;
      const controles = Array.from(form.querySelectorAll('button[type="submit"]'));
      enviando = true;
      for (const boton of controles) boton.disabled = true;
      detenerLectura();
      estado.textContent = t('Esperando respuesta de la IA…');
      try {
        const respuesta = await fetch(form.action, { method: 'POST', body: datos, signal });
        const pagina = new DOMParser().parseFromString(await respuesta.text(), 'text/html');
        const actualizada = pagina.querySelector('[data-chat-voz]');
        if (actualizada?.dataset.chatVoz === seccion.dataset.chatVoz) {
          const nuevaRespuesta = actualizada.querySelectorAll(selectorRespuestas).length > respuestas.length;
          eventos.abort();
          seccion.replaceWith(actualizada);
          prepararChat(actualizada, nuevaRespuesta);
          const destino = actualizada.querySelector(fueTeclado ? '[data-voz-mensaje]' : '[data-voz-dictar]:not([hidden])');
          destino?.focus({ preventScroll: true });
          const conversacion = actualizada.querySelector('.chat-container');
          if (conversacion) conversacion.scrollTop = conversacion.scrollHeight;
        } else if (respuesta.redirected) {
          window.location.assign(respuesta.url);
        } else {
          estado.textContent = t('No se pudo confirmar el envío. Revisa la conversación antes de intentar de nuevo.');
        }
      } catch (error) {
        if (error.name !== 'AbortError') estado.textContent = t('No se pudo confirmar el envío. Revisa la conversación antes de intentar de nuevo.');
      } finally {
        enviando = false;
        for (const boton of controles) boton.disabled = false;
      }
    }, { signal });

    window.addEventListener('pagehide', () => {
      soltar();
      detenerLectura();
    }, { signal });
    if (leerAlAbrir) {
      if (document.hidden) document.addEventListener('visibilitychange', leerRespuesta, { once: true, signal });
      else leerRespuesta();
    }
  }

  const seccion = document.querySelector('[data-chat-voz]');
  if (seccion) prepararChat(seccion, seccion.hasAttribute('data-voz-inicial'));
})();
