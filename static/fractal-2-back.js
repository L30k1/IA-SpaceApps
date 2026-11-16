(() => {
  const { t } = window.mediSpaceLanguage;
  const data = JSON.parse(document.querySelector('#f2b-datos').textContent);
  const form_data = document.querySelector('#f2b-form');
  const startTest = document.querySelector('#f2b-iniciar');
  const roundContainer = document.querySelector('#f2b-ronda');
  const respond = document.querySelector('#f2b-responder');
  const progress = document.querySelector('#f2b-avance');
  const confirmation = document.querySelector('#f2b-confirmacion');
  const state = document.querySelector('#f2b-estado');
  const retryButton = document.querySelector('#f2b-reintentar');
  const restart = document.querySelector('#f2b-reiniciar');
  const canvas = respond.querySelector('canvas');
  const context = canvas.getContext('2d');
  if (!context) {
    announce(t("This browser cannot display the test shapes."));
    return;
  }

  const answers = Array(data.secuencia.length).fill(null);
  let index_score = 0;
  let isRunning = false;
  let offset = null;
  let nextStep;

  function announce(message_text) {
    state.hidden = false;
    state.textContent = message_text;
  }

  function draw(shape) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = '#bfdbfe';
    context.lineCap = 'round';
    const amplitude = [0.51, 0.73, 0.98, 1.18][shape % 4];
    const axes = [3, 4, 5][Math.floor(shape / 4)];
    const rotation = Math.PI / 2 + (shape % 4) * 0.45;

    function forkRecord(x, y, angle, lengthValue, level) {
      const endX = x + Math.cos(angle) * lengthValue;
      const endY = y + Math.sin(angle) * lengthValue;
      context.lineWidth = 1 + level * 0.7;
      context.beginPath();
      context.moveTo(x, y);
      context.lineTo(endX, endY);
      context.stroke();
      if (level === 0) return;
      forkRecord(endX, endY, angle - amplitude, lengthValue * 0.56, level - 1);
      forkRecord(endX, endY, angle + amplitude, lengthValue * 0.56, level - 1);
    }

    for (let axis = 0; axis < axes; axis++) {
      const angle = rotation + axis * 2 * Math.PI / axes;
      forkRecord(canvas.width / 2, canvas.height / 2, angle, 58, 4);
    }
  }

  function display() {
    if (!isRunning) return;
    respond.removeAttribute('data-registrada');
    confirmation.textContent = '';
    progress.textContent = t("Figure {actual} of {total}", { actual: index_score + 1, total: answers.length });
    draw(data.secuencia[index_score]);
    offset = performance.now();
    nextStep = setTimeout(() => {
      offset = null;
      index_score += 1;
      if (index_score === answers.length) {
        isRunning = false;
        roundContainer.hidden = true;
        save();
      } else {
        requestAnimationFrame(display);
      }
    }, data.exposicion_ms);
  }

  function mark() {
    if (!isRunning || offset === null || answers[index_score] !== null) return;
    const elapsedMs = performance.now() - offset;
    if (elapsedMs >= data.exposicion_ms) return;
    answers[index_score] = elapsedMs;
    respond.setAttribute('data-registrada', '');
    confirmation.textContent = confirmation.dataset.mensaje;
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
    respond.focus({ preventScroll: true });
    requestAnimationFrame(display);
  });
  respond.addEventListener('click', mark);
  document.addEventListener('keydown', event => {
    if (event.code !== 'Space' || !isRunning) return;
    event.preventDefault();
    if (!event.repeat) mark();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !isRunning) return;
    isRunning = false;
    clearTimeout(nextStep);
    roundContainer.hidden = true;
    announce(t("The test stopped when you left the tab. Start a new round to measure your times."));
    restart.hidden = false;
  });
  retryButton.addEventListener('click', save);
  startTest.disabled = false;
})();
