(() => {
  const { t, locale } = window.mediSpaceLanguage;
  const seccion = document.querySelector('[data-emergencia]');
  const panel = seccion?.querySelector('[data-voz-emergencia]');
  if (!panel) return;

  const form = panel.closest('form');
  const mensaje = form.elements.mensaje;
  const enviar = form.querySelector('[type="submit"]');
  const conversacion = seccion.querySelector('.chat-psicologico');
  const microfono = panel.querySelector('[data-emergencia-mic]');
  const estado = panel.querySelector('[data-voz-estado]');
  const botonLeer = panel.querySelector('[data-voz-escuchar]');
  const reproductor = window.crearAudioIA(panel, 'psicologico');
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const reconocimiento = Reconocimiento && window.isSecureContext ? new Reconocimiento() : null;
  const idioma = locale;
  const errores = {
    'not-allowed': t('Pulsa Activar micrófono y concede permiso en el navegador. También puedes escribir.'),
    'service-not-allowed': t('El navegador no permite el dictado. Puedes escribir tu mensaje.'),
    'audio-capture': t('No se encontró un micrófono. Puedes escribir tu mensaje.'),
    network: t('El servicio de dictado no está disponible. Puedes escribir tu mensaje.'),
  };
  let activo = false;
  let capturando = false;
  let cerrando = false;
  let descartado = false;
  let enviando = false;
  let ultima = conversacion.querySelector('li:last-child:not(.mensaje-usuario) p')?.textContent.trim();
  let pausa;
  let reintento;
  let transcripcion = '';

  function cambiarMicrofono(encendido) {
    activo = encendido;
    microfono.textContent = encendido ? t('Detener micrófono') : t('Activar micrófono');
    microfono.setAttribute('aria-pressed', String(encendido));
  }

  function descartarCaptura() {
    clearTimeout(pausa);
    clearTimeout(reintento);
    if (capturando) {
      descartado = true;
      reconocimiento.abort();
    }
  }

  function detenerVoz(aviso) {
    cambiarMicrofono(false);
    descartarCaptura();
    detenerLectura();
    estado.textContent = aviso;
  }

  function escuchar() {
    if (!activo || capturando || enviando || reproductor.enCurso) return;
    transcripcion = '';
    descartado = false;
    cerrando = false;
    try {
      reconocimiento.start();
      capturando = true;
      estado.textContent = t('Activando micrófono…');
    } catch {
      detenerVoz(errores['not-allowed']);
    }
  }

  function cerrarFrase() {
    clearTimeout(pausa);
    if (!capturando || cerrando || descartado) return;
    cerrando = true;
    reconocimiento.stop();
  }

  function detenerLectura() {
    reproductor.detener();
    botonLeer.textContent = t('Escuchar última respuesta');
  }

  function leerRespuesta(texto, manual = false) {
    if (!reproductor.disponible || (!activo && !manual && !reproductor.nubeElegida)) {
      estado.textContent = t('Respuesta disponible en el chat.');
      escuchar();
      return;
    }
    descartarCaptura();
    botonLeer.textContent = t('Detener lectura');
    estado.textContent = activo
      ? t('La IA está respondiendo. El micrófono está en pausa.')
      : t('Reproduciendo la respuesta de la IA…');
    reproductor.leer(texto, exito => {
      botonLeer.textContent = t('Escuchar última respuesta');
      estado.textContent = exito ? '' : t('Para oír esta respuesta, pulsa Escuchar última respuesta.');
      escuchar();
    }, () => {
      estado.textContent = t('ElevenLabs no está disponible. Se intenta usar la voz del navegador.');
    });
  }

  botonLeer.hidden = !ultima || !reproductor.disponible;
  botonLeer.addEventListener('click', () => {
    if (enviando) return;
    if (reproductor.enCurso) {
      detenerLectura();
      escuchar();
    } else if (ultima) leerRespuesta(ultima, true);
  });

  function agregarTurno(turnos) {
    conversacion.querySelector('#ultimo-mensaje')?.removeAttribute('id');
    for (const turno of turnos) {
      const item = document.createElement('li');
      const autor = document.createElement('strong');
      const texto = document.createElement('p');
      const esUsuario = turno.role === 'user';
      if (esUsuario) item.className = 'mensaje-usuario';
      autor.textContent = esUsuario ? t('Tú') : t('IA');
      texto.textContent = turno.text;
      item.append(autor, texto);
      conversacion.append(item);
    }
    conversacion.lastElementChild.id = 'ultimo-mensaje';
    conversacion.lastElementChild.scrollIntoView({ block: 'nearest' });
  }

  async function enviarTurno() {
    if (enviando || !mensaje.value.trim()) return;
    enviando = true;
    descartarCaptura();
    const datos = new FormData(form);
    mensaje.readOnly = true;
    enviar.disabled = true;
    estado.textContent = t('Enviando a la IA…');
    let turnos;
    try {
      const respuesta = await fetch(form.action, {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: datos,
      });
      const resultado = await respuesta.json();
      if (respuesta.ok) {
        form.elements.revision.value = resultado.revision;
        mensaje.value = '';
        turnos = resultado.mensajes;
      } else {
        detenerVoz(resultado.error);
      }
    } catch {
      detenerVoz(t('No se pudo confirmar el envío. Conserva tu mensaje y revisa el chat antes de reenviarlo.'));
    } finally {
      enviando = false;
      mensaje.readOnly = false;
      enviar.disabled = false;
    }
    if (turnos) {
      agregarTurno(turnos);
      ultima = turnos.at(-1).text;
      botonLeer.hidden = !reproductor.disponible;
      leerRespuesta(ultima);
    }
  }

  form.addEventListener('submit', evento => {
    evento.preventDefault();
    detenerLectura();
    enviarTurno();
  });
  mensaje.addEventListener('input', () => {
    if (activo) detenerVoz(t('Micrófono detenido mientras escribes.'));
  });

  window.addEventListener('pagehide', () => detenerVoz(t('Micrófono detenido al salir del chat.')));
  if (!reconocimiento) {
    estado.textContent = t('El dictado requiere un navegador compatible y una conexión segura. Puedes escribir tu mensaje.');
    return;
  }

  reconocimiento.lang = idioma;
  reconocimiento.continuous = true;
  reconocimiento.interimResults = true;
  reconocimiento.onstart = () => {
    if (activo && !descartado) estado.textContent = t('Micrófono activo. Habla cuando quieras.');
  };
  reconocimiento.onspeechstart = () => clearTimeout(pausa);
  reconocimiento.onspeechend = cerrarFrase;
  reconocimiento.onresult = evento => {
    if (descartado) return;
    transcripcion = Array.from(evento.results, resultado => resultado[0].transcript.trim())
      .join(' ').trim().slice(0, mensaje.maxLength);
    if (!transcripcion) return;
    mensaje.value = transcripcion;
    clearTimeout(pausa);
    if (!cerrando) pausa = setTimeout(cerrarFrase, 1100);
  };
  reconocimiento.onerror = evento => {
    if (descartado || evento.error === 'no-speech' || evento.error === 'aborted') return;
    detenerVoz(errores[evento.error] || t('Falló el dictado. Vuelve a activar el micrófono o escribe tu mensaje.'));
  };
  reconocimiento.onend = () => {
    capturando = false;
    clearTimeout(pausa);
    if (!activo) return;
    if (transcripcion && !descartado) enviarTurno();
    else reintento = setTimeout(escuchar, 300);
  };

  function activarVoz() {
    if (mensaje.value.trim()) {
      estado.textContent = t('Envía o borra el borrador antes de activar el micrófono.');
      return;
    }
    cambiarMicrofono(true);
    escuchar();
  }

  microfono.hidden = false;
  microfono.addEventListener('click', () => {
    if (activo) detenerVoz(t('Micrófono detenido.'));
    else activarVoz();
  });
  activarVoz();
})();
