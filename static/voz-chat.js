(() => {
  const panel = document.querySelector('[data-voz-chat]');
  if (!panel) return;

  const idioma = 'es-MX';
  const mensaje = panel.closest('form').querySelector('[data-voz-mensaje]');
  const respuestas = panel.closest('.view, .info-card').querySelectorAll('[data-voz-respuesta]');
  const ultimaRespuesta = respuestas[respuestas.length - 1]?.textContent.trim();
  const dictar = panel.querySelector('[data-voz-dictar]');
  const escuchar = panel.querySelector('[data-voz-escuchar]');
  const elevenlabs = panel.querySelector('[data-voz-elevenlabs]');
  const audio = panel.querySelector('[data-voz-audio]');
  const estado = panel.querySelector('[data-voz-estado]');
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const sintesis = window.speechSynthesis;
  let grabando = false;
  let fraseActiva = null;

  if (elevenlabs && ultimaRespuesta) {
    let urlAudio = null;
    const peticion = new AbortController();
    elevenlabs.hidden = false;
    panel.querySelector('[data-voz-aviso-elevenlabs]').hidden = false;
    audio.addEventListener('play', () => {
      if (grabando) {
        audio.pause();
        return;
      }
      if (fraseActiva) {
        terminarLectura();
        sintesis.cancel();
      }
      dictar.disabled = true;
    });
    for (const evento of ['pause', 'ended']) {
      audio.addEventListener(evento, () => {
        if (!fraseActiva && !grabando) dictar.disabled = false;
      });
    }
    elevenlabs.addEventListener('click', async () => {
      if (grabando || elevenlabs.disabled) return;
      elevenlabs.disabled = true;
      estado.textContent = 'Generando audio con ElevenLabs…';
      try {
        const datos = new FormData();
        datos.set('csrf', panel.closest('form').elements.csrf.value);
        datos.set('turno', panel.dataset.vozTurno);
        const respuesta = await fetch(panel.dataset.vozUrl, { method: 'POST', body: datos, signal: peticion.signal });
        if (!respuesta.ok) {
          const detalle = await respuesta.json().catch(() => null);
          throw new Error(detalle?.error || 'ElevenLabs no respondió. Puedes usar la voz del navegador.');
        }
        const archivo = await respuesta.blob();
        if (archivo.type !== 'audio/mpeg' || !archivo.size) throw new Error('ElevenLabs no devolvió audio.');
        urlAudio = URL.createObjectURL(archivo);
        audio.src = urlAudio;
        audio.hidden = false;
        elevenlabs.hidden = true;
        estado.textContent = 'Audio generado con ElevenLabs.';
        if (!grabando) await audio.play().catch(() => {
          estado.textContent = 'Audio generado con ElevenLabs. Pulsa Reproducir en el reproductor.';
        });
      } catch (error) {
        if (error.name !== 'AbortError') estado.textContent = error.message || 'Puedes usar la voz del navegador.';
      } finally {
        elevenlabs.disabled = false;
      }
    });
    window.addEventListener('pagehide', (evento) => {
      audio.pause();
      if (evento.persisted) return;
      peticion.abort();
      if (urlAudio) URL.revokeObjectURL(urlAudio);
    });
  }

  function terminarLectura() {
    fraseActiva = null;
    escuchar.textContent = 'Escuchar última respuesta';
    dictar.disabled = false;
  }

  if (ultimaRespuesta && sintesis && window.SpeechSynthesisUtterance) {
    escuchar.hidden = false;
    escuchar.addEventListener('click', () => {
      audio?.pause();
      if (fraseActiva) {
        terminarLectura();
        sintesis.cancel();
        return;
      }
      const frase = new window.SpeechSynthesisUtterance(ultimaRespuesta);
      frase.lang = idioma;
      const voces = sintesis.getVoices().filter(voz => voz.localService && /^es(?:-|$)/i.test(voz.lang));
      const voz = voces.find(opcion => opcion.lang.toLowerCase() === idioma.toLowerCase()) || voces[0];
      if (voz) frase.voice = voz;
      frase.onend = () => {
        if (fraseActiva === frase) terminarLectura();
      };
      frase.onerror = () => {
        if (fraseActiva !== frase) return;
        terminarLectura();
        estado.textContent = 'El navegador no pudo reproducir la respuesta.';
      };
      fraseActiva = frase;
      escuchar.textContent = 'Detener lectura';
      dictar.disabled = true;
      estado.textContent = '';
      sintesis.speak(frase);
    });
  }

  if (Reconocimiento && window.isSecureContext) {
    const reconocimiento = new Reconocimiento();
    reconocimiento.lang = idioma;
    reconocimiento.continuous = false;
    reconocimiento.interimResults = false;
    const errores = {
      'not-allowed': 'Autoriza el micrófono en el navegador para dictar.',
      'service-not-allowed': 'El navegador no permite el servicio de dictado.',
      'audio-capture': 'No se encontró un micrófono disponible.',
      'no-speech': 'No se detectó voz. Puedes intentar de nuevo.',
      'network': 'El servicio de dictado no está disponible. Puedes escribir tu mensaje.',
    };
    let hayResultado = false;
    let huboError = false;

    function terminarDictado() {
      grabando = false;
      dictar.disabled = false;
      dictar.textContent = 'Dictar mensaje';
      escuchar.disabled = false;
    }

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
        ? 'Se alcanzó el límite de caracteres. Revisa el mensaje antes de enviarlo.'
        : 'Dictado listo. Revisa el mensaje y pulsa Enviar.';
    };
    reconocimiento.onerror = (evento) => {
      huboError = true;
      estado.textContent = errores[evento.error] || 'El navegador no pudo transcribir el mensaje.';
    };
    reconocimiento.onend = () => {
      terminarDictado();
      if (!hayResultado && !huboError) estado.textContent = 'No se detectó voz. Puedes intentar de nuevo.';
    };
    dictar.hidden = false;
    panel.querySelector('[data-voz-aviso]').hidden = false;
    dictar.addEventListener('click', () => {
      if (grabando) {
        reconocimiento.stop();
        dictar.disabled = true;
        estado.textContent = 'Terminando el dictado…';
        return;
      }
      hayResultado = false;
      huboError = false;
      try {
        reconocimiento.start();
        grabando = true;
        escuchar.disabled = true;
        dictar.textContent = 'Detener dictado';
        estado.textContent = 'Escuchando…';
      } catch {
        terminarDictado();
        estado.textContent = 'No se pudo iniciar el dictado.';
      }
    });
    window.addEventListener('pagehide', () => {
      if (grabando) reconocimiento.abort();
    });
  }

  window.addEventListener('pagehide', () => {
    if (fraseActiva) sintesis.cancel();
  });
  panel.hidden = false;
  if (dictar.hidden && escuchar.hidden && (!elevenlabs || elevenlabs.hidden)) {
    estado.textContent = Reconocimiento && !window.isSecureContext
      ? 'El dictado requiere HTTPS o abrir MediSpace en localhost.'
      : 'Este navegador no tiene controles de voz disponibles para este chat.';
  }
})();
