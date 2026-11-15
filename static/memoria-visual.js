(() => {
  const reloj = document.querySelector('#volt-espera');
  if (reloj) {
    const boton = document.querySelector('#volt-diferido');
    const fin = Date.now() + Number(reloj.dataset.segundos) * 1000;
    function actualizarEspera() {
      const restante = Math.max(0, Math.ceil((fin - Date.now()) / 1000));
      if (restante === 0) {
        reloj.textContent = 'Ya puedes iniciar el reconocimiento diferido.';
        boton.disabled = false;
        return;
      }
      const minutos = Math.floor(restante / 60);
      const segundos = String(restante % 60).padStart(2, '0');
      reloj.textContent = `Tiempo restante: ${minutos}:${segundos}`;
      setTimeout(actualizarEspera, 1000);
    }
    actualizarEspera();
  }

  const datos = document.querySelector('#volt-estimulos');
  if (!datos) return;
  const { aprendizaje, reconocimiento, exposicion, fase } = JSON.parse(datos.textContent);
  const formulario = document.querySelector('#volt-form');
  const estado = document.querySelector('#volt-estado');
  const comenzar = document.querySelector('#volt-comenzar');
  const lienzo = document.querySelector('#volt-figura');
  const contexto = lienzo.getContext('2d');
  const opciones = document.querySelector('#volt-opciones');
  const reintentar = document.querySelector('#volt-reintentar');
  if (!contexto) {
    estado.textContent = 'Este navegador no puede dibujar los estímulos de la prueba.';
    return;
  }

  const respuestas = [];
  let figuraAprendida = 0;
  let aprendizajeActivo = false;
  let tiempoExpuesto = 0;
  let inicioExposicion = null;
  let temporizador;
  let presentado = null;
  let pausa = null;

  const vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]];
  const caras = [
    { indices: [1, 3, 7, 5], color: '#247ab4' },
    { indices: [2, 3, 7, 6], color: '#3897ca' },
    { indices: [4, 5, 7, 6], color: '#92d6f4' },
  ];

  function dibujar(figura) {
    const cubos = [...figura].sort((a, b) => (a[0] + a[1] + a[2]) - (b[0] + b[1] + b[2]));
    const proyectados = cubos.map(([x, y, z]) => vertices.map(([dx, dy, dz]) => [
      (x + dx - y - dy) * 21,
      (x + dx + y + dy - 2 * (z + dz)) * 12,
    ]));
    const puntos = proyectados.flat();
    const xs = puntos.map(([x]) => x);
    const ys = puntos.map(([, y]) => y);
    const margenX = (lienzo.width - Math.min(...xs) - Math.max(...xs)) / 2;
    const margenY = (lienzo.height - Math.min(...ys) - Math.max(...ys)) / 2;
    contexto.clearRect(0, 0, lienzo.width, lienzo.height);
    contexto.lineWidth = 1.5;
    contexto.strokeStyle = '#0a2642';
    for (const cubo of proyectados) {
      for (const cara of caras) {
        contexto.beginPath();
        const [x, y] = cubo[cara.indices[0]];
        contexto.moveTo(x + margenX, y + margenY);
        for (const indice of cara.indices.slice(1)) {
          const [px, py] = cubo[indice];
          contexto.lineTo(px + margenX, py + margenY);
        }
        contexto.closePath();
        contexto.fillStyle = cara.color;
        contexto.fill();
        contexto.stroke();
      }
    }
  }

  function mostrarReconocimiento() {
    estado.textContent = `${fase === 'diferido' ? 'Reconocimiento diferido' : 'Reconocimiento inmediato'}. Figura ${respuestas.length + 1} de ${reconocimiento.length}.`;
    dibujar(reconocimiento[respuestas.length]);
    opciones.hidden = false;
    presentado = performance.now();
  }

  function continuarExposicion() {
    if (document.hidden) return;
    inicioExposicion = performance.now();
    temporizador = setTimeout(() => {
      inicioExposicion = null;
      tiempoExpuesto = 0;
      figuraAprendida += 1;
      if (figuraAprendida < aprendizaje.length) {
        mostrarAprendizaje();
      } else {
        aprendizajeActivo = false;
        requestAnimationFrame(mostrarReconocimiento);
      }
    }, exposicion * 1000 - tiempoExpuesto);
  }

  function mostrarAprendizaje() {
    estado.textContent = `Aprendizaje. Figura ${figuraAprendida + 1} de ${aprendizaje.length}.`;
    dibujar(aprendizaje[figuraAprendida]);
    continuarExposicion();
  }

  async function guardar() {
    reintentar.hidden = true;
    estado.textContent = 'Guardando respuestas…';
    try {
      const datosEnvio = new FormData(formulario);
      datosEnvio.set('accion', fase === 'diferido' ? 'diferido' : 'inmediato');
      datosEnvio.set('respuestas', JSON.stringify(respuestas));
      const respuesta = await fetch(formulario.action, { method: 'POST', body: datosEnvio, redirect: 'error' });
      const resultado = await respuesta.json();
      if (respuesta.ok && resultado.url) {
        window.location.replace(resultado.url);
        return;
      }
      estado.textContent = resultado.error || 'No se pudieron guardar las respuestas.';
    } catch {
      estado.textContent = 'No se pudo confirmar el guardado. Puedes reintentar sin responder otra vez.';
    }
    reintentar.hidden = false;
    reintentar.focus();
  }

  comenzar.addEventListener('click', () => {
    comenzar.hidden = true;
    lienzo.hidden = false;
    if (aprendizaje.length) {
      requestAnimationFrame(() => {
        aprendizajeActivo = true;
        mostrarAprendizaje();
      });
    } else {
      requestAnimationFrame(mostrarReconocimiento);
    }
  });

  opciones.addEventListener('click', (evento) => {
    const opcion = evento.target.closest('button[data-vista]');
    if (!opcion || presentado === null || document.hidden) return;
    respuestas.push({ vista: opcion.dataset.vista === 'si', tiempo_ms: performance.now() - presentado });
    presentado = null;
    if (respuestas.length < reconocimiento.length) {
      requestAnimationFrame(mostrarReconocimiento);
    } else {
      lienzo.hidden = true;
      opciones.hidden = true;
      guardar();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (inicioExposicion !== null) {
        clearTimeout(temporizador);
        tiempoExpuesto += performance.now() - inicioExposicion;
        inicioExposicion = null;
      }
      if (presentado !== null) pausa = performance.now();
    } else {
      if (aprendizajeActivo && inicioExposicion === null) continuarExposicion();
      if (pausa !== null && presentado !== null) presentado += performance.now() - pausa;
      pausa = null;
    }
  });

  reintentar.addEventListener('click', guardar);
  comenzar.disabled = false;
})();
