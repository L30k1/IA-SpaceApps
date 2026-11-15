const inicio = document.querySelector('#praxis-inicio');
const estado = document.querySelector('#praxis-estado');
const tablero = document.querySelector('#praxis-tablero');
const objetivo = document.querySelector('#praxis-objetivo');
const resultados = document.querySelector('#praxis-resultados');
const listaTiempos = document.querySelector('#praxis-tiempos');
const totalObjetivos = 20;
const ladoInicial = 76;
const reduccion = 2;
const tiempos = [];
const formato = new Intl.NumberFormat('es', { maximumFractionDigits: 0 });
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

function terminarRonda(mensaje) {
  cancelAnimationFrame(cuadroPendiente);
  cuadroPendiente = 0;
  rondaActiva = false;
  aparicion = null;
  tablero.hidden = true;
  objetivo.hidden = true;
  estado.textContent = mensaje;
  inicio.textContent = 'Repetir prueba';
  inicio.hidden = false;
  inicio.focus();
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
  terminarRonda(`Prueba completada. Tiempo medio de reacción de ${milisegundos(promedio)}.`);
}

inicio.addEventListener('click', () => {
  tiempos.length = 0;
  rondaActiva = true;
  inicio.hidden = true;
  resultados.hidden = true;
  tablero.hidden = false;
  estado.hidden = false;
  estado.textContent = `Objetivos completados: 0 de ${totalObjetivos}`;
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
  estado.textContent = `Objetivos completados: ${tiempos.length} de ${totalObjetivos}`;
  mostrarObjetivo();
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden && rondaActiva) {
    terminarRonda('La prueba se interrumpió al salir de la pestaña. Inicia otra ronda para medir tus tiempos.');
  }
});

inicio.disabled = false;
