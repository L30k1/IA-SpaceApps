(() => {
  const { t } = window.mediSpaceLanguage;
  const datos = JSON.parse(document.querySelector('#emociones-datos').textContent);
  const formulario = document.querySelector('#emociones-form');
  const iniciar = document.querySelector('#emociones-iniciar');
  const ronda = document.querySelector('#emociones-ronda');
  const opciones = document.querySelector('#emociones-opciones');
  const avance = document.querySelector('#emociones-avance');
  const estado = document.querySelector('#emociones-estado');
  const reintentar = document.querySelector('#emociones-reintentar');
  const reiniciar = document.querySelector('#emociones-reiniciar');
  const lienzo = document.querySelector('#emociones-rostro');
  const contexto = lienzo.getContext('2d');
  const respuestas = [];
  let laminas;
  let activa = false;
  let desde = null;
  let exposicion;

  function informar(texto) {
    estado.hidden = false;
    estado.textContent = texto;
  }

  async function cargar() {
    if (!contexto) {
      informar(t('Este navegador no puede dibujar los estímulos de la prueba.'));
      return;
    }
    informar(t('Cargando rostros…'));
    try {
      laminas = Object.fromEntries(await Promise.all(Object.entries(datos.laminas).map(async ([nombre, url]) => {
        const imagen = new Image();
        imagen.src = url;
        await imagen.decode();
        return [nombre, imagen];
      })));
      estado.hidden = true;
      iniciar.disabled = false;
    } catch {
      informar(t('No se pudieron cargar los rostros. Vuelve a abrir la prueba.'));
      reiniciar.hidden = false;
    }
  }

  function mostrar() {
    if (!activa) return;
    const { lamina, casilla } = datos.ensayos[respuestas.length];
    const imagen = laminas[lamina];
    const ancho = imagen.naturalWidth / 4;
    const alto = imagen.naturalHeight / 3;
    avance.textContent = t('Rostro {actual} de {total}', { actual: respuestas.length + 1, total: datos.ensayos.length });
    contexto.drawImage(imagen, casilla % 4 * ancho, Math.floor(casilla / 4) * alto, ancho, alto,
      0, 0, lienzo.width, lienzo.height);
    exposicion = setTimeout(() => {
      contexto.clearRect(0, 0, lienzo.width, lienzo.height);
      opciones.disabled = false;
      desde = performance.now();
      opciones.querySelector('button').focus({ preventScroll: true });
    }, datos.exposicion_ms);
  }

  async function guardar() {
    reintentar.hidden = true;
    informar(t('Guardando los resultados…'));
    try {
      const cuerpo = new FormData(formulario);
      cuerpo.set('respuestas', JSON.stringify(respuestas));
      const respuesta = await fetch(formulario.action, { method: 'POST', body: cuerpo, redirect: 'error' });
      const resultado = await respuesta.json();
      if (respuesta.ok && resultado.url) {
        window.location.replace(resultado.url);
        return;
      }
      informar(resultado.error || t('No se pudieron guardar los resultados.'));
    } catch {
      informar(t('No se pudo confirmar el guardado. Puedes reintentar sin repetir la prueba.'));
    }
    reintentar.hidden = false;
    reintentar.focus();
  }

  iniciar.addEventListener('click', () => {
    activa = true;
    iniciar.hidden = true;
    ronda.hidden = false;
    requestAnimationFrame(mostrar);
  });
  opciones.addEventListener('click', evento => {
    const boton = evento.target.closest('[data-emocion]');
    if (!boton || !activa || desde === null) return;
    respuestas.push({ emocion: boton.dataset.emocion, tiempo_ms: performance.now() - desde });
    desde = null;
    opciones.disabled = true;
    if (respuestas.length < datos.ensayos.length) {
      requestAnimationFrame(mostrar);
    } else {
      activa = false;
      ronda.hidden = true;
      guardar();
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !activa) return;
    activa = false;
    clearTimeout(exposicion);
    ronda.hidden = true;
    informar(t('La prueba se interrumpió al salir de la pestaña. Inicia otra ronda para medir tus tiempos.'));
    reiniciar.hidden = false;
  });
  reintentar.addEventListener('click', guardar);
  cargar();
})();
