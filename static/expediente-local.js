(() => {
  "use strict";
  const { t } = window.mediSpaceLanguage;

  const storageKey = "medispace.archivo-local";
  const writeMode = { mode: "readwrite" };
  const byteLimit = 8 * 1024 * 1024;
  const supported = window.isSecureContext && typeof window.showOpenFilePicker === "function"
    && window.indexedDB && navigator.locks && window.crypto?.subtle;

  function fileStore(chat_mode, operation) {
    return new Promise((resolve, reject) => {
      const openRequest = indexedDB.open("medispace", 1);
      openRequest.onupgradeneeded = () => openRequest.result.createObjectStore("archivos");
      openRequest.onerror = () => reject(openRequest.error);
      openRequest.onsuccess = () => {
        const database = openRequest.result;
        try {
          const transaction = database.transaction("archivos", chat_mode);
          const requestController = operation(transaction.objectStore("archivos"));
          transaction.oncomplete = () => {
            database.close();
            resolve(requestController.result);
          };
          transaction.onabort = () => {
            database.close();
            reject(transaction.error);
          };
        } catch (error) {
          database.close();
          reject(error);
        }
      };
    });
  }

  function parseRecord(content_blob) {
    try {
      const document = JSON.parse(new TextDecoder().decode(content_blob));
      if (typeof document?._id === "string" && document._id.trim()) {
        return document;
      }
    } catch {
      // Only JSON files that identify a medical record are accepted.
    }
    throw new Error(t("The file does not contain a valid medical record ID."));
  }

  async function fingerprint(content_blob) {
    const hash = await crypto.subtle.digest("SHA-256", content_blob);
    return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
  }

  function mergeEntries(local, serverRecord, field_name) {
    const prior_entries = local[field_name] ?? [];
    const currentEntries = serverRecord[field_name] ?? [];
    if (!Array.isArray(prior_entries) || !Array.isArray(currentEntries)) {
      throw new Error(t("Review the entries in the original file before updating it."));
    }
    const ids = new Set(currentEntries.map(entry => entry.id));
    return [...currentEntries, ...prior_entries.filter(entry => !ids.has(entry?.id))];
  }

  async function readFileHandle(handle) {
    const uploaded_file = await handle.getFile();
    if (uploaded_file.size > byteLimit) {
      throw new Error(t("The file exceeds the size limit."));
    }
    return { archivo: uploaded_file, contenido: await uploaded_file.arrayBuffer() };
  }

  async function chooseFile() {
    const [handle] = await window.showOpenFilePicker({
      multiple: false,
      excludeAcceptAllOption: true,
      types: [{ description: t("MediSpace medical record"), accept: { "application/json": [".json"] } }],
    });
    const { archivo: uploaded_file, contenido: content_blob } = await readFileHandle(handle);
    return {
      archivo: uploaded_file, handle, expedienteId: parseRecord(content_blob)._id.trim(), huella: await fingerprint(content_blob),
    };
  }

  async function requestWritePermission(handle) {
    if (await handle.queryPermission(writeMode) === "granted") {
      return true;
    }
    try {
      return await handle.requestPermission(writeMode) === "granted";
    } catch (error) {
      // Some browsers require a second click after the picker closes.
      if (error.name !== "SecurityError") throw error;
      return false;
    }
  }

  async function linkRecord({ handle, expedienteId: recordId, huella: hash }) {
    const link = { handle, expedienteId: recordId, huella: hash };
    const lookup_key = sessionStorage.getItem(storageKey) || crypto.randomUUID();
    await fileStore("readwrite", storage => storage.put(link, lookup_key));
    sessionStorage.setItem(storageKey, lookup_key);
    return link;
  }

  function setupForm() {
    const form_data = document.getElementById("auth-form");
    const input = document.getElementById("expediente");
    const button = document.getElementById("elegir-expediente-local");
    const state = document.getElementById("estado-expediente-local");
    if (!input) return;

    const display = message => {
      state.hidden = false;
      state.textContent = message;
    };
    form_data.addEventListener("submit", event => {
      if (!input.files.length) {
        event.preventDefault();
        display(t("Choose your JSON file to continue."));
        button.focus();
      }
    });
    input.required = false;
    input.hidden = true;
    button.hidden = false;
    const submitTurn = document.getElementById("btn-auth-submit");
    button.addEventListener("click", async () => {
      button.disabled = true;
      submitTurn.disabled = true;
      try {
        const selection = await chooseFile();
        const authorized = await requestWritePermission(selection.handle);
        const requestBody = new DataTransfer();
        requestBody.items.add(selection.archivo);
        await linkRecord(selection);
        input.files = requestBody.files;
        display(authorized
          ? t("Linked file: {nombre}.", { nombre: selection.archivo.name })
          : t("File selected. You can allow writing from Results."));
      } catch (error) {
        if (error.name !== "AbortError") {
          input.hidden = false;
          input.required = true;
          button.hidden = true;
          display(t("You can select the JSON file here and link the original later from Results."));
          input.focus();
        }
      } finally {
        button.disabled = false;
        submitTurn.disabled = false;
      }
    });
  }

  async function setupResults(panel) {
    const state = document.getElementById("estado-archivo-local");
    const linkButton = document.getElementById("vincular-archivo-local");
    const saveButton = document.getElementById("guardar-archivo-local");
    const { expedienteId: recordId, url, auto } = panel.dataset;
    const display = message => { state.textContent = message; };
    panel.hidden = false;
    if (!supported) {
      display(t("To update the original file from this page, open MediSpace in Chrome or Edge."));
      return;
    }

    const lookup_key = sessionStorage.getItem(storageKey);
    const previous_value = lookup_key ? await fileStore("readonly", storage => storage.get(lookup_key)) : null;
    let link = previous_value?.expedienteId === recordId ? previous_value : null;
    saveButton.hidden = !link;
    linkButton.hidden = false;
    display(link ? t("Linked file: {nombre}.", { nombre: link.handle.name }) : t("Link the file you uploaded to update it."));

    async function save() {
      if (await link.handle.queryPermission(writeMode) !== "granted") {
        display(t("Select “Update original file” to allow writing."));
        return;
      }
      await navigator.locks.request(`medispace-expediente-${recordId}`, async () => {
        const currentKey = sessionStorage.getItem(storageKey);
        const stored = await fileStore("readonly", storage => storage.get(currentKey));
        if (!stored || stored.expedienteId !== recordId) {
          throw new Error(t("Link the file for this record again."));
        }
        const reply = await fetch(url, { cache: "no-store", redirect: "error" });
        if (!reply.ok || !reply.headers.get("Content-Type")?.includes("application/json")) {
          throw new Error(t("The record could not be retrieved. Check your session."));
        }
        const serverRecord = parseRecord(await reply.arrayBuffer());
        const { contenido: content_blob } = await readFileHandle(stored.handle);
        const local = parseRecord(content_blob);
        if (serverRecord._id.trim() !== recordId || local._id.trim() !== recordId) {
          throw new Error(t("The selected file belongs to a different record."));
        }
        const mergedEntries = { ...local, chequeos: mergeEntries(local, serverRecord, "chequeos") };
        delete mergedEntries.clave_edicion_hash;
        for (const field_name of ["alergias", "antecedentes", "medicamentos", "estado_alergias", "referencias_monitoreo"]) {
          if (Object.hasOwn(serverRecord, field_name)) mergedEntries[field_name] = serverRecord[field_name];
        }
        if (Array.isArray(local.misiones) && Array.isArray(serverRecord.misiones)) {
          const targets = new Map(serverRecord.misiones.map(mission => [mission.id, mission.ejercicio_min_diarios]));
          mergedEntries.misiones = local.misiones.map(mission => {
            if (!targets.has(mission.id)) return mission;
            const refreshedForm = { ...mission };
            const goal = targets.get(mission.id);
            if (goal === undefined) delete refreshedForm.ejercicio_min_diarios;
            else refreshedForm.ejercicio_min_diarios = goal;
            return refreshedForm;
          });
        }
        for (const field_name of [
          "diario_psicologico", "semanal_psicologico", "praxis_motora", "memoria_visual",
          "orientacion_linea", "fractal_2_back", "reconocimiento_emociones", "sesiones_ejercicio",
        ]) {
          if (field_name in serverRecord || field_name in local) {
            mergedEntries[field_name] = mergeEntries(local, serverRecord, field_name);
          }
        }
        const updated_record = new TextEncoder().encode(JSON.stringify(mergedEntries, null, 2) + "\n");
        const hash = await fingerprint(updated_record);
        const localHash = await fingerprint(content_blob);
        if (localHash !== hash && localHash !== stored.huella) {
          throw new Error(t("The file changed outside MediSpace. Review it and link it again to update it."));
        }
        if (localHash !== hash) {
          const speechFlow = await stored.handle.createWritable({ mode: "exclusive" });
          try {
            await speechFlow.write(updated_record);
            await speechFlow.close();
          } catch (error) {
            await speechFlow.abort().catch(() => {});
            throw error;
          }
          await fileStore("readwrite", storage => storage.put({ ...stored, huella: hash }, currentKey));
        }
        display(t("Original file updated: {nombre}.", { nombre: stored.handle.name }));
      });
    }

    async function execute(operation) {
      saveButton.disabled = true;
      linkButton.disabled = true;
      try {
        await operation();
      } catch (error) {
        if (error.name !== "AbortError") display(error.message || t("The original file could not be updated."));
      } finally {
        saveButton.disabled = false;
        linkButton.disabled = false;
      }
    }

    saveButton.addEventListener("click", () => execute(async () => {
      if (await requestWritePermission(link.handle)) {
        await save();
      } else {
        display(t("Allow write access in your browser to update this file."));
      }
    }));
    linkButton.addEventListener("click", () => execute(async () => {
      const selection = await chooseFile();
      if (selection.expedienteId !== recordId) {
        throw new Error(t("The selected file belongs to a different record."));
      }
      const authorized = await requestWritePermission(selection.handle);
      link = await linkRecord(selection);
      saveButton.hidden = false;
      if (authorized) {
        await save();
      } else {
        display(t("Select “Update original file” to allow writing."));
      }
    }));
    if (link && auto === "1") await execute(save);
  }

  if (supported && document.getElementById("auth-form")) setupForm();
  const panel = document.getElementById("archivo-local");
  if (panel) setupResults(panel).catch(() => {
    document.getElementById("estado-archivo-local").textContent = t("The browser could not retrieve the linked file.");
  });
})();
