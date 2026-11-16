(() => {
  const form_data = document.querySelector('[data-crear-cuenta]');
  if (!form_data) return;

  const { t } = window.mediSpaceLanguage;
  const notice = document.querySelector('[data-historial-error]');
  const errorMessage = t("The medical record could not be generated. Please try again.");
  let isGenerating = false;

  function showError(message) {
    notice.textContent = message;
    notice.hidden = false;
    notice.scrollIntoView({ block: 'nearest' });
  }

  form_data.addEventListener('submit', async event => {
    if (isGenerating) {
      event.preventDefault();
      return;
    }
    if (event.submitter && event.submitter.value !== 'descargar') return;

    event.preventDefault();
    isGenerating = true;
    notice.hidden = true;
    const data = new FormData(form_data);
    data.set('accion', 'descargar');
    const buttons = [...form_data.querySelectorAll('button[type="submit"]:enabled')];
    buttons.forEach(button => { button.disabled = true; });

    try {
      const reply = await fetch(form_data.action, {
        method: 'POST', body: data, headers: { Accept: 'application/json' },
      });
      const disposition = reply.headers.get('Content-Disposition') || '';
      if (!reply.ok || !disposition.startsWith('attachment')) {
        const resultData = await reply.json().catch(() => null);
        showError(resultData?.error || errorMessage);
        return;
      }
      const url = URL.createObjectURL(await reply.blob());
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      const link = document.createElement('a');
      link.href = url;
      link.download = disposition.match(/filename="([^"]+)"/)?.[1] || 'expediente.json';
      document.body.append(link);
      link.click();
      link.remove();
      await new Promise(resolve => setTimeout(resolve, 100));
      window.location.assign(form_data.dataset.crearCuenta);
    } catch {
      showError(errorMessage);
    } finally {
      isGenerating = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  });
})();
