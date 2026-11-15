(() => {
  const { t } = window.mediSpaceLanguage;
  const datos = JSON.parse(document.querySelector('#lot-datos').textContent);
  const formulario = document.querySelector('#lot-form');
  const iniciar = document.querySelector('#lot-iniciar');
  const diagrama = document.querySelector('#lot-diagrama');
  const estado = document.querySelector('#lot-estado');
  const controles = document.querySelector('#lot-controles');
  const opciones = document.querySelectorAll('#lot-opciones button');
  const confirmar = document.querySelector('#lot-confirmar');
  const reintentar = document.querySelector('#lot-reintentar');
  const contexto = diagrama.getContext('2d');
  if (!contexto) {
    estado.hidden = false;
    estado.textContent = t('Este navegador no puede dibujar las líneas de la prueba.');
    return;
  }

  const respuestas = [];
  const seleccionadas = new Set();
  let inicioPar = null;

  function punto(x, y, angulo, distancia) {
    const radianes = angulo * Math.PI / 180;
    return [x + Math.cos(radianes) * distancia, y - Math.sin(radianes) * distancia];
  }

  function linea(origen, destino, color, ancho) {
    contexto.beginPath();
    contexto.moveTo(...origen);
    contexto.lineTo(...destino);
    contexto.strokeStyle = color;
    contexto.lineWidth = ancho;
    contexto.stroke();
  }

  function dibujar() {
    contexto.clearRect(0, 0, diagrama.width, diagrama.height);
    const par = datos.rondas[respuestas.length];
    par.forEach((angulo, indice) => {
      const x = 145 + indice * 190;
      linea(punto(x, 64, angulo, -38), punto(x, 64, angulo, 38), '#e0f2fe', 4);
    });
    contexto.font = '600 19px Inter, sans-serif';
    contexto.textAlign = 'center';
    contexto.textBaseline = 'middle';
    datos.angulos.forEach((angulo, indice) => {
      const numero = indice + 1;
      const seleccionada = seleccionadas.has(numero);
      const color = seleccionada ? '#fbbf24' : '#7dd3fc';
      linea([240, 282], punto(240, 282, angulo, 140), color, seleccionada ? 4 : 2);
      contexto.fillStyle = seleccionada ? color : '#f0f6ff';
      contexto.fillText(numero, ...punto(240, 282, angulo, 160));
    });
  }

  function actualizarSeleccion() {
    opciones.forEach((boton) => {
      const elegida = seleccionadas.has(Number(boton.dataset.linea));
      boton.setAttribute('aria-pressed', String(elegida));
      boton.disabled = !elegida && seleccionadas.size === 2;
    });
    confirmar.disabled = seleccionadas.size !== 2;
  }

  function mostrarPar() {
    seleccionadas.clear();
    actualizarSeleccion();
    dibujar();
    estado.textContent = t('Par {actual} de {total}. Selecciona dos líneas.', { actual: respuestas.length + 1, total: datos.rondas.length });
    inicioPar = performance.now();
    opciones[0].focus();
  }

  async function guardar() {
    reintentar.hidden = true;
    estado.textContent = t('Guardando los resultados…');
    try {
      const datosEnvio = new FormData(formulario);
      datosEnvio.set('respuestas', JSON.stringify(respuestas));
      const respuesta = await fetch(formulario.action, { method: 'POST', body: datosEnvio, redirect: 'error' });
      const resultado = await respuesta.json();
      if (respuesta.ok && resultado.url) {
        window.location.replace(resultado.url);
        return;
      }
      estado.textContent = resultado.error || t('No se pudieron guardar los resultados.');
    } catch {
      estado.textContent = t('No se pudo confirmar el guardado. Puedes reintentar sin repetir la prueba.');
    }
    reintentar.hidden = false;
    reintentar.focus();
  }

  iniciar.addEventListener('click', () => {
    iniciar.hidden = true;
    estado.hidden = false;
    diagrama.hidden = false;
    controles.hidden = false;
    requestAnimationFrame(mostrarPar);
  });

  opciones.forEach((boton) => boton.addEventListener('click', () => {
    if (inicioPar === null) return;
    const numero = Number(boton.dataset.linea);
    if (seleccionadas.has(numero)) seleccionadas.delete(numero);
    else if (seleccionadas.size < 2) seleccionadas.add(numero);
    actualizarSeleccion();
    dibujar();
  }));

  confirmar.addEventListener('click', () => {
    if (inicioPar === null || seleccionadas.size !== 2) return;
    respuestas.push({ lineas: [...seleccionadas], tiempo_ms: performance.now() - inicioPar });
    inicioPar = null;
    confirmar.disabled = true;
    if (respuestas.length < datos.rondas.length) {
      requestAnimationFrame(mostrarPar);
    } else {
      diagrama.hidden = true;
      controles.hidden = true;
      guardar();
    }
  });

  reintentar.addEventListener('click', guardar);
  iniciar.disabled = false;
})();
