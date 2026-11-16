(() => {
  const { t } = window.mediSpaceLanguage;
  const countdown = document.querySelector('#volt-espera');
  if (countdown) {
    const button = document.querySelector('#volt-diferido');
    const end = Date.now() + Number(countdown.dataset.segundos) * 1000;
    function updateCountdown() {
      const remainingTime = Math.max(0, Math.ceil((end - Date.now()) / 1000));
      if (remainingTime === 0) {
        countdown.textContent = t("You can now start delayed recognition.");
        button.disabled = false;
        return;
      }
      const minutes_count = Math.floor(remainingTime / 60);
      const seconds = String(remainingTime % 60).padStart(2, '0');
      countdown.textContent = t("Time remaining: {tiempo}", { tiempo: `${minutes_count}:${seconds}` });
      setTimeout(updateCountdown, 1000);
    }
    updateCountdown();
  }

  const data = document.querySelector('#volt-estimulos');
  if (!data) return;
  const { aprendizaje: learning, reconocimiento: recognition_round, exposicion: exposure, fase: phase } = JSON.parse(data.textContent);
  const form_data = document.querySelector('#volt-form');
  const state = document.querySelector('#volt-estado');
  const startRound = document.querySelector('#volt-comenzar');
  const canvas = document.querySelector('#volt-figura');
  const context = canvas.getContext('2d');
  const options = document.querySelector('#volt-opciones');
  const retryButton = document.querySelector('#volt-reintentar');
  if (!context) {
    state.textContent = t("This browser cannot display the test shapes.");
    return;
  }

  const answers = [];
  let learnedShape = 0;
  let learningActive = false;
  let exposureTime = 0;
  let exposureStartedAt = null;
  let timer;
  let presentedAt = null;
  let pauseTime = null;

  const vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]];
  const faces = [
    { indices: [1, 3, 7, 5], color: '#247ab4' },
    { indices: [2, 3, 7, 6], color: '#3897ca' },
    { indices: [4, 5, 7, 6], color: '#92d6f4' },
  ];

  function draw(shape) {
    const cubes = [...shape].sort((a, b) => (a[0] + a[1] + a[2]) - (b[0] + b[1] + b[2]));
    const projected = cubes.map(([x, y, z]) => vertices.map(([dx, dy, dz]) => [
      (x + dx - y - dy) * 21,
      (x + dx + y + dy - 2 * (z + dz)) * 12,
    ]));
    const points = projected.flat();
    const xs = points.map(([x]) => x);
    const ys = points.map(([, y]) => y);
    const marginX = (canvas.width - Math.min(...xs) - Math.max(...xs)) / 2;
    const marginY = (canvas.height - Math.min(...ys) - Math.max(...ys)) / 2;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.lineWidth = 1.5;
    context.strokeStyle = '#0a2642';
    for (const cube of projected) {
      for (const face of faces) {
        context.beginPath();
        const [x, y] = cube[face.indices[0]];
        context.moveTo(x + marginX, y + marginY);
        for (const index_score of face.indices.slice(1)) {
          const [px, py] = cube[index_score];
          context.lineTo(px + marginX, py + marginY);
        }
        context.closePath();
        context.fillStyle = face.color;
        context.fill();
        context.stroke();
      }
    }
  }

  function showRecognition() {
    state.textContent = t("{fase}. Shape {actual} of {total}.", {
      fase: phase === 'diferido' ? t("Delayed recognition") : t("Immediate recognition"),
      actual: answers.length + 1, total: recognition_round.length,
    });
    draw(recognition_round[answers.length]);
    options.hidden = false;
    presentedAt = performance.now();
  }

  function resumeExposure() {
    if (document.hidden) return;
    exposureStartedAt = performance.now();
    timer = setTimeout(() => {
      exposureStartedAt = null;
      exposureTime = 0;
      learnedShape += 1;
      if (learnedShape < learning.length) {
        displayLearningPhase();
      } else {
        learningActive = false;
        requestAnimationFrame(showRecognition);
      }
    }, exposure * 1000 - exposureTime);
  }

  function displayLearningPhase() {
    state.textContent = t("Learning phase. Shape {actual} of {total}.", { actual: learnedShape + 1, total: learning.length });
    draw(learning[learnedShape]);
    resumeExposure();
  }

  async function save() {
    retryButton.hidden = true;
    state.textContent = t("Saving responses…");
    try {
      const submission = new FormData(form_data);
      submission.set('accion', phase === 'diferido' ? 'diferido' : 'inmediato');
      submission.set('respuestas', JSON.stringify(answers));
      const reply = await fetch(form_data.action, { method: 'POST', body: submission, redirect: 'error' });
      const resultData = await reply.json();
      if (reply.ok && resultData.url) {
        window.location.replace(resultData.url);
        return;
      }
      state.textContent = resultData.error || t("The responses could not be saved.");
    } catch {
      state.textContent = t("Saving could not be confirmed. You can retry without answering again.");
    }
    retryButton.hidden = false;
    retryButton.focus();
  }

  startRound.addEventListener('click', () => {
    startRound.hidden = true;
    canvas.hidden = false;
    if (learning.length) {
      requestAnimationFrame(() => {
        learningActive = true;
        displayLearningPhase();
      });
    } else {
      requestAnimationFrame(showRecognition);
    }
  });

  options.addEventListener('click', (event) => {
    const option = event.target.closest('button[data-vista]');
    if (!option || presentedAt === null || document.hidden) return;
    answers.push({ vista: option.dataset.vista === 'si', tiempo_ms: performance.now() - presentedAt });
    presentedAt = null;
    if (answers.length < recognition_round.length) {
      requestAnimationFrame(showRecognition);
    } else {
      canvas.hidden = true;
      options.hidden = true;
      save();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (exposureStartedAt !== null) {
        clearTimeout(timer);
        exposureTime += performance.now() - exposureStartedAt;
        exposureStartedAt = null;
      }
      if (presentedAt !== null) pauseTime = performance.now();
    } else {
      if (learningActive && exposureStartedAt === null) resumeExposure();
      if (pauseTime !== null && presentedAt !== null) presentedAt += performance.now() - pauseTime;
      pauseTime = null;
    }
  });

  retryButton.addEventListener('click', save);
  startRound.disabled = false;
})();
