(() => {
  const formulario = document.querySelector('[data-crear-cuenta]');
  if (!formulario) return;

  const { t } = window.mediSpaceLanguage;
  const aviso = document.querySelector('[data-historial-error]');
  const mensajeError = t('No se pudo generar el historial médico. Inténtalo de nuevo.');
  let generando = false;

  function mostrarError(mensaje) {
    aviso.textContent = mensaje;
    aviso.hidden = false;
    aviso.scrollIntoView({ block: 'nearest' });
  }

  formulario.addEventListener('submit', async evento => {
    if (generando) {
      evento.preventDefault();
      return;
    }
    if (evento.submitter && evento.submitter.value !== 'descargar') return;

    evento.preventDefault();
    generando = true;
    aviso.hidden = true;
    const datos = new FormData(formulario);
    datos.set('accion', 'descargar');
    const botones = [...formulario.querySelectorAll('button[type="submit"]:enabled')];
    botones.forEach(boton => { boton.disabled = true; });

    try {
      const respuesta = await fetch(formulario.action, {
        method: 'POST', body: datos, headers: { Accept: 'application/json' },
      });
      const disposicion = respuesta.headers.get('Content-Disposition') || '';
      if (!respuesta.ok || !disposicion.startsWith('attachment')) {
        const resultado = await respuesta.json().catch(() => null);
        mostrarError(resultado?.error || mensajeError);
        return;
      }
      const url = URL.createObjectURL(await respuesta.blob());
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = disposicion.match(/filename="([^"]+)"/)?.[1] || 'expediente.json';
      document.body.append(enlace);
      enlace.click();
      enlace.remove();
      await new Promise(resolve => setTimeout(resolve, 100));
      window.location.assign(formulario.dataset.crearCuenta);
    } catch {
      mostrarError(mensajeError);
    } finally {
      generando = false;
      botones.forEach(boton => { boton.disabled = false; });
    }
  });
})();
