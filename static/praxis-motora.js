const { t, locale } = window.mediSpaceLanguage;
const start = document.querySelector('#praxis-inicio');
const state = document.querySelector('#praxis-estado');
const board = document.querySelector('#praxis-tablero');
const targetSquare = document.querySelector('#praxis-objetivo');
const resultados = document.querySelector('#praxis-resultados');
const responseTimes = document.querySelector('#praxis-tiempos');
const form_data = document.querySelector('#praxis-envio');
const retryButton = document.querySelector('#praxis-reintentar');
const targetCount = Number(form_data.dataset.objetivos);
const initialSize = 76;
const scaleFactor = 2;
const times = [];
const format = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
let roundActive = false;
let shownAt = null;
let pendingFrame = 0;

function milliseconds(elapsedMs) {
  return `${format.format(elapsedMs)} ms`;
}

function showTarget() {
  pendingFrame = requestAnimationFrame(() => {
    pendingFrame = 0;
    targetSquare.style.setProperty('--lado', `${initialSize - times.length * scaleFactor}px`);
    targetSquare.style.setProperty('--x', Math.random());
    targetSquare.style.setProperty('--y', Math.random());
    targetSquare.hidden = false;
    shownAt = performance.now();
  });
}

function finishRound() {
  cancelAnimationFrame(pendingFrame);
  pendingFrame = 0;
  roundActive = false;
  shownAt = null;
  board.hidden = true;
  targetSquare.hidden = true;
}

function showResults() {
  const promedio = times.reduce((totalSum, elapsedMs) => totalSum + elapsedMs, 0) / targetCount;
  document.querySelector('#praxis-promedio').textContent = milliseconds(promedio);
  document.querySelector('#praxis-mejor').textContent = milliseconds(Math.min(...times));
  responseTimes.replaceChildren(...times.map((elapsedMs) => {
    const item = document.createElement('li');
    item.textContent = milliseconds(elapsedMs);
    return item;
  }));
  resultados.hidden = false;
  finishRound();
  saveResults();
}

async function saveResults() {
  retryButton.hidden = true;
  state.textContent = t("Saving results…");
  try {
    const data = new FormData(form_data);
    data.set('tiempos_ms', JSON.stringify(times));
    const reply = await fetch(form_data.action, { method: 'POST', body: data, redirect: 'error' });
    const resultData = await reply.json();
    if (!reply.ok || !resultData.url) {
      state.textContent = resultData.error || t("The results could not be saved.");
    } else {
      window.location.replace(resultData.url);
      return;
    }
  } catch {
    state.textContent = t("Saving could not be confirmed. You can retry without repeating the test.");
  }
  retryButton.hidden = false;
  retryButton.focus();
}

retryButton.addEventListener('click', saveResults);

start.addEventListener('click', () => {
  times.length = 0;
  roundActive = true;
  start.hidden = true;
  resultados.hidden = true;
  board.hidden = false;
  state.hidden = false;
  state.textContent = t("Targets completed: {actual} of {total}", { actual: 0, total: targetCount });
  showTarget();
});

targetSquare.addEventListener('click', (event) => {
  if (shownAt === null || event.detail === 0) return;
  times.push(performance.now() - shownAt);
  shownAt = null;
  targetSquare.hidden = true;
  if (times.length === targetCount) {
    showResults();
    return;
  }
  state.textContent = t("Targets completed: {actual} of {total}", { actual: times.length, total: targetCount });
  showTarget();
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden && roundActive) {
    finishRound();
    state.textContent = t("The test stopped when you left the tab. Start a new round to measure your times.");
    start.textContent = t("Repeat test");
    start.hidden = false;
    start.focus();
  }
});

start.disabled = false;
