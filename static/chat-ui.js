(() => {
  const { t } = window.mediSpaceLanguage;

  function scrollToLatest(conversation) {
    if (conversation) conversation.scrollTop = conversation.scrollHeight;
  }

  function appendMessage(conversation, turn, pending = false) {
    const item = document.createElement('li');
    const speaker = document.createElement('strong');
    const message_text = document.createElement('p');
    const isUser = turn.role === 'user';
    item.className = isUser ? 'chat-turno chat-turno-usuario' : 'chat-turno';
    if (pending) item.classList.add('chat-turno-pendiente');
    speaker.textContent = isUser ? t("You") : t("AI");
    message_text.textContent = turn.text;
    if (!isUser) message_text.setAttribute('data-voz-respuesta', '');
    item.append(speaker, message_text);
    conversation.append(item);
    scrollToLatest(conversation);
    return item;
  }

  window.mediSpaceChat = { appendMessage, scrollToLatest };
})();
