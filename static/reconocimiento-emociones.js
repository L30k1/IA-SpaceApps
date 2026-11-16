(() => {
  const { t } = window.mediSpaceLanguage;
  const data = JSON.parse(document.querySelector('#emociones-datos').textContent);
  const form_data = document.querySelector('#emociones-form');
  const startTest = document.querySelector('#emociones-iniciar');
  const roundContainer = document.querySelector('#emociones-ronda');
  const options = document.querySelector('#emociones-opciones');
  const progress = document.querySelector('#emociones-avance');
  const state = document.querySelector('#emociones-estado');
  const retryButton = document.querySelector('#emociones-reintentar');
  const restart = document.querySelector('#emociones-reiniciar');
  const canvas = document.querySelector('#emociones-rostro');
  const context = canvas.getContext('2d');
  const answers = [];
  let sheets;
  let isRunning = false;
  let offset = null;
  let exposure;

  function announce(message_text) {
    state.hidden = false;
    state.textContent = message_text;
  }

  async function loadAssets() {
    if (!context) {
      announce(t("This browser cannot display the test shapes."));
      return;
    }
    announce(t("Loading faces…"));
    try {
      sheets = Object.fromEntries(await Promise.all(Object.entries(data.laminas).map(async ([fileName, url]) => {
        const image = new Image();
        image.src = url;
        await image.decode();
        return [fileName, image];
      })));
      state.hidden = true;
      startTest.disabled = false;
    } catch {
      announce(t("The faces did not load. Reopen the test."));
      restart.hidden = false;
    }
  }

  function display() {
    if (!isRunning) return;
    const { lamina: sheet, casilla: cell } = data.ensayos[answers.length];
    const image = sheets[sheet];
    const width = image.naturalWidth / 4;
    const height = image.naturalHeight / 3;
    progress.textContent = t("Face {actual} of {total}", { actual: answers.length + 1, total: data.ensayos.length });
    context.drawImage(image, cell % 4 * width, Math.floor(cell / 4) * height, width, height,
      0, 0, canvas.width, canvas.width);
    context.fillStyle = '#071229';
    context.fillRect(0, canvas.width, canvas.width, canvas.height - canvas.width);
    context.fillStyle = '#f0f6ff';
    context.font = '600 19px sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(t("AI-generated image"), canvas.width / 2, (canvas.width + canvas.height) / 2);
    exposure = setTimeout(() => {
      context.clearRect(0, 0, canvas.width, canvas.height);
      options.disabled = false;
      offset = performance.now();
      options.querySelector('button').focus({ preventScroll: true });
    }, data.exposicion_ms);
  }

  async function save() {
    retryButton.hidden = true;
    announce(t("Saving results…"));
    try {
      const payload = new FormData(form_data);
      payload.set('respuestas', JSON.stringify(answers));
      const reply = await fetch(form_data.action, { method: 'POST', body: payload, redirect: 'error' });
      const resultData = await reply.json();
      if (reply.ok && resultData.url) {
        window.location.replace(resultData.url);
        return;
      }
      announce(resultData.error || t("The results could not be saved."));
    } catch {
      announce(t("Saving could not be confirmed. You can retry without repeating the test."));
    }
    retryButton.hidden = false;
    retryButton.focus();
  }

  startTest.addEventListener('click', () => {
    isRunning = true;
    startTest.hidden = true;
    roundContainer.hidden = false;
    requestAnimationFrame(display);
  });
  options.addEventListener('click', event => {
    const button = event.target.closest('[data-emocion]');
    if (!button || !isRunning || offset === null) return;
    answers.push({ emocion: button.dataset.emocion, tiempo_ms: performance.now() - offset });
    offset = null;
    options.disabled = true;
    if (answers.length < data.ensayos.length) {
      requestAnimationFrame(display);
    } else {
      isRunning = false;
      roundContainer.hidden = true;
      save();
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !isRunning) return;
    isRunning = false;
    clearTimeout(exposure);
    roundContainer.hidden = true;
    announce(t("The test stopped when you left the tab. Start a new round to measure your times."));
    restart.hidden = false;
  });
  retryButton.addEventListener('click', save);
  loadAssets();
})();
