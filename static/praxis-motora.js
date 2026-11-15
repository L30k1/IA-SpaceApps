const { t, locale } = window.mediSpaceLanguage;
const inicio = document.querySelector('#praxis-inicio');
const estado = document.querySelector('#praxis-estado');
const tablero = document.querySelector('#praxis-tablero');
const objetivo = document.querySelector('#praxis-objetivo');
const resultados = document.querySelector('#praxis-resultados');
const listaTiempos = document.querySelector('#praxis-tiempos');
const formulario = document.querySelector('#praxis-envio');
const reintentar = document.querySelector('#praxis-reintentar');
const totalObjetivos = Number(formulario.dataset.objetivos);
const ladoInicial = 76;
const reduccion = 2;
const tiempos = [];
const formato = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
let rondaActiva = false;
let aparicion = null;
let cuadroPendiente = 0;

function milisegundos(tiempo) {
  return `${formato.format(tiempo)} ms`;
}

function mostrarObjetivo() {
  cuadroPendiente = requestAnimationFrame(() => {
    cuadroPendiente = 0;
    objetivo.style.setProperty('--lado', `${ladoInicial - tiempos.length * reduccion}px`);
    objetivo.style.setProperty('--x', Math.random());
    objetivo.style.setProperty('--y', Math.random());
    objetivo.hidden = false;
    aparicion = performance.now();
  });
}

function terminarRonda() {
  cancelAnimationFrame(cuadroPendiente);
  cuadroPendiente = 0;
  rondaActiva = false;
  aparicion = null;
  tablero.hidden = true;
  objetivo.hidden = true;
}

function mostrarResultados() {
  const promedio = tiempos.reduce((suma, tiempo) => suma + tiempo, 0) / totalObjetivos;
  document.querySelector('#praxis-promedio').textContent = milisegundos(promedio);
  document.querySelector('#praxis-mejor').textContent = milisegundos(Math.min(...tiempos));
  listaTiempos.replaceChildren(...tiempos.map((tiempo) => {
    const item = document.createElement('li');
    item.textContent = milisegundos(tiempo);
    return item;
  }));
  resultados.hidden = false;
  terminarRonda();
  guardarResultados();
}

async function guardarResultados() {
  reintentar.hidden = true;
  estado.textContent = t('Guardando los resultados…');
  try {
    const datos = new FormData(formulario);
    datos.set('tiempos_ms', JSON.stringify(tiempos));
    const respuesta = await fetch(formulario.action, { method: 'POST', body: datos, redirect: 'error' });
    const resultado = await respuesta.json();
    if (!respuesta.ok || !resultado.url) {
      estado.textContent = resultado.error || t('No se pudieron guardar los resultados.');
    } else {
      window.location.replace(resultado.url);
      return;
    }
  } catch {
    estado.textContent = t('No se pudo confirmar el guardado. Puedes reintentar sin repetir la prueba.');
  }
  reintentar.hidden = false;
  reintentar.focus();
}

reintentar.addEventListener('click', guardarResultados);

inicio.addEventListener('click', () => {
  tiempos.length = 0;
  rondaActiva = true;
  inicio.hidden = true;
  resultados.hidden = true;
  tablero.hidden = false;
  estado.hidden = false;
  estado.textContent = t('Objetivos completados: {actual} de {total}', { actual: 0, total: totalObjetivos });
  mostrarObjetivo();
});

objetivo.addEventListener('click', (evento) => {
  if (aparicion === null || evento.detail === 0) return;
  tiempos.push(performance.now() - aparicion);
  aparicion = null;
  objetivo.hidden = true;
  if (tiempos.length === totalObjetivos) {
    mostrarResultados();
    return;
  }
  estado.textContent = t('Objetivos completados: {actual} de {total}', { actual: tiempos.length, total: totalObjetivos });
  mostrarObjetivo();
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden && rondaActiva) {
    terminarRonda();
    estado.textContent = t('La prueba se interrumpió al salir de la pestaña. Inicia otra ronda para medir tus tiempos.');
    inicio.textContent = t('Repetir prueba');
    inicio.hidden = false;
    inicio.focus();
  }
});

inicio.disabled = false;
