(() => {
  const { t } = window.mediSpaceLanguage;
  const data = JSON.parse(document.querySelector('#lot-datos').textContent);
  const form_data = document.querySelector('#lot-form');
  const startTest = document.querySelector('#lot-iniciar');
  const diagram = document.querySelector('#lot-diagrama');
  const state = document.querySelector('#lot-estado');
  const controls = document.querySelector('#lot-controles');
  const options = document.querySelectorAll('#lot-opciones button');
  const confirmAction = document.querySelector('#lot-confirmar');
  const retryButton = document.querySelector('#lot-reintentar');
  const context = diagram.getContext('2d');
  if (!context) {
    state.hidden = false;
    state.textContent = t("This browser cannot display the test lines.");
    return;
  }

  const answers = [];
  const selections = new Set();
  let trialStartedAt = null;

  function point(x, y, angle, distance) {
    const radians = angle * Math.PI / 180;
    return [x + Math.cos(radians) * distance, y - Math.sin(radians) * distance];
  }

  function line(origin, destination, color, width) {
    context.beginPath();
    context.moveTo(...origin);
    context.lineTo(...destination);
    context.strokeStyle = color;
    context.lineWidth = width;
    context.stroke();
  }

  function draw() {
    context.clearRect(0, 0, diagram.width, diagram.height);
    const pair = data.rondas[answers.length];
    pair.forEach((angle, index_score) => {
      const x = 145 + index_score * 190;
      line(point(x, 64, angle, -38), point(x, 64, angle, 38), '#e0f2fe', 4);
    });
    context.font = '600 19px Inter, sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    data.angulos.forEach((angle, index_score) => {
      const number = index_score + 1;
      const selected = selections.has(number);
      const color = selected ? '#fbbf24' : '#7dd3fc';
      line([240, 282], point(240, 282, angle, 140), color, selected ? 4 : 2);
      context.fillStyle = selected ? color : '#f0f6ff';
      context.fillText(number, ...point(240, 282, angle, 160));
    });
  }

  function updateSelection() {
    options.forEach((button) => {
      const chosenFile = selections.has(Number(button.dataset.linea));
      button.setAttribute('aria-pressed', String(chosenFile));
      button.disabled = !chosenFile && selections.size === 2;
    });
    confirmAction.disabled = selections.size !== 2;
  }

  function showPair() {
    selections.clear();
    updateSelection();
    draw();
    state.textContent = t("Pair {actual} of {total}. Select two lines.", { actual: answers.length + 1, total: data.rondas.length });
    trialStartedAt = performance.now();
    options[0].focus();
  }

  async function save() {
    retryButton.hidden = true;
    state.textContent = t("Saving results…");
    try {
      const submission = new FormData(form_data);
      submission.set('respuestas', JSON.stringify(answers));
      const reply = await fetch(form_data.action, { method: 'POST', body: submission, redirect: 'error' });
      const resultData = await reply.json();
      if (reply.ok && resultData.url) {
        window.location.replace(resultData.url);
        return;
      }
      state.textContent = resultData.error || t("The results could not be saved.");
    } catch {
      state.textContent = t("Saving could not be confirmed. You can retry without repeating the test.");
    }
    retryButton.hidden = false;
    retryButton.focus();
  }

  startTest.addEventListener('click', () => {
    startTest.hidden = true;
    state.hidden = false;
    diagram.hidden = false;
    controls.hidden = false;
    requestAnimationFrame(showPair);
  });

  options.forEach((button) => button.addEventListener('click', () => {
    if (trialStartedAt === null) return;
    const number = Number(button.dataset.linea);
    if (selections.has(number)) selections.delete(number);
    else if (selections.size < 2) selections.add(number);
    updateSelection();
    draw();
  }));

  confirmAction.addEventListener('click', () => {
    if (trialStartedAt === null || selections.size !== 2) return;
    answers.push({ lineas: [...selections], tiempo_ms: performance.now() - trialStartedAt });
    trialStartedAt = null;
    confirmAction.disabled = true;
    if (answers.length < data.rondas.length) {
      requestAnimationFrame(showPair);
    } else {
      diagram.hidden = true;
      controls.hidden = true;
      save();
    }
  });

  retryButton.addEventListener('click', save);
  startTest.disabled = false;
})();
