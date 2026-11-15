(() => {
  const { t } = window.mediSpaceLanguage;
  const datos = JSON.parse(document.querySelector('#f2b-datos').textContent);
  const formulario = document.querySelector('#f2b-form');
  const iniciar = document.querySelector('#f2b-iniciar');
  const ronda = document.querySelector('#f2b-ronda');
  const responder = document.querySelector('#f2b-responder');
  const avance = document.querySelector('#f2b-avance');
  const estado = document.querySelector('#f2b-estado');
  const reintentar = document.querySelector('#f2b-reintentar');
  const reiniciar = document.querySelector('#f2b-reiniciar');
  const lienzo = responder.querySelector('canvas');
  const contexto = lienzo.getContext('2d');
  if (!contexto) {
    informar(t('Este navegador no puede dibujar los estímulos de la prueba.'));
    return;
  }

  const respuestas = Array(datos.secuencia.length).fill(null);
  let indice = 0;
  let activa = false;
  let desde = null;
  let siguiente;

  function informar(texto) {
    estado.hidden = false;
    estado.textContent = texto;
  }

  function dibujar(figura) {
    contexto.clearRect(0, 0, lienzo.width, lienzo.height);
    contexto.strokeStyle = '#bfdbfe';
    contexto.lineCap = 'round';
    const amplitud = [0.51, 0.73, 0.98, 1.18][figura % 4];
    const ejes = [3, 4, 5][Math.floor(figura / 4)];
    const giro = Math.PI / 2 + (figura % 4) * 0.45;

    function ramificar(x, y, angulo, largo, nivel) {
      const finX = x + Math.cos(angulo) * largo;
      const finY = y + Math.sin(angulo) * largo;
      contexto.lineWidth = 1 + nivel * 0.7;
      contexto.beginPath();
      contexto.moveTo(x, y);
      contexto.lineTo(finX, finY);
      contexto.stroke();
      if (nivel === 0) return;
      ramificar(finX, finY, angulo - amplitud, largo * 0.56, nivel - 1);
      ramificar(finX, finY, angulo + amplitud, largo * 0.56, nivel - 1);
    }

    for (let eje = 0; eje < ejes; eje++) {
      const angulo = giro + eje * 2 * Math.PI / ejes;
      ramificar(lienzo.width / 2, lienzo.height / 2, angulo, 58, 4);
    }
  }

  function mostrar() {
    if (!activa) return;
    avance.textContent = t('Figura {actual} de {total}', { actual: indice + 1, total: respuestas.length });
    dibujar(datos.secuencia[indice]);
    desde = performance.now();
    siguiente = setTimeout(() => {
      desde = null;
      indice += 1;
      if (indice === respuestas.length) {
        activa = false;
        ronda.hidden = true;
        guardar();
      } else {
        requestAnimationFrame(mostrar);
      }
    }, datos.exposicion_ms);
  }

  function marcar() {
    if (!activa || desde === null || respuestas[indice] !== null) return;
    const tiempo = performance.now() - desde;
    if (tiempo < datos.exposicion_ms) respuestas[indice] = tiempo;
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
    responder.focus({ preventScroll: true });
    requestAnimationFrame(mostrar);
  });
  responder.addEventListener('click', marcar);
  document.addEventListener('keydown', evento => {
    if (evento.code !== 'Space' || !activa) return;
    evento.preventDefault();
    if (!evento.repeat) marcar();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !activa) return;
    activa = false;
    clearTimeout(siguiente);
    ronda.hidden = true;
    informar(t('La prueba se interrumpió al salir de la pestaña. Inicia otra ronda para medir tus tiempos.'));
    reiniciar.hidden = false;
  });
  reintentar.addEventListener('click', guardar);
  iniciar.disabled = false;
})();
