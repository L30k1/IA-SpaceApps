(() => {
  const { t } = window.mediSpaceLanguage;

  function desplazar(conversacion) {
    if (conversacion) conversacion.scrollTop = conversacion.scrollHeight;
  }

  function agregar(conversacion, turno, pendiente = false) {
    const item = document.createElement('li');
    const autor = document.createElement('strong');
    const texto = document.createElement('p');
    const esUsuario = turno.role === 'user';
    item.className = esUsuario ? 'chat-turno chat-turno-usuario' : 'chat-turno';
    if (pendiente) item.classList.add('chat-turno-pendiente');
    autor.textContent = esUsuario ? t('Tú') : t('IA');
    texto.textContent = turno.text;
    if (!esUsuario) texto.setAttribute('data-voz-respuesta', '');
    item.append(autor, texto);
    conversacion.append(item);
    desplazar(conversacion);
    return item;
  }

  window.interfazChat = { agregar, desplazar };
})();
