(() => {
  "use strict";

  const storageKey = "medispace.archivo-local";
  const escritura = { mode: "readwrite" };
  const limiteBytes = 8 * 1024 * 1024;
  const soportado = window.isSecureContext && typeof window.showOpenFilePicker === "function"
    && window.indexedDB && navigator.locks && window.crypto?.subtle;

  function archivos(modo, operacion) {
    return new Promise((resolve, reject) => {
      const apertura = indexedDB.open("medispace", 1);
      apertura.onupgradeneeded = () => apertura.result.createObjectStore("archivos");
      apertura.onerror = () => reject(apertura.error);
      apertura.onsuccess = () => {
        const database = apertura.result;
        try {
          const transaccion = database.transaction("archivos", modo);
          const peticion = operacion(transaccion.objectStore("archivos"));
          transaccion.oncomplete = () => {
            database.close();
            resolve(peticion.result);
          };
          transaccion.onabort = () => {
            database.close();
            reject(transaccion.error);
          };
        } catch (error) {
          database.close();
          reject(error);
        }
      };
    });
  }

  function leerDocumento(contenido) {
    try {
      const documento = JSON.parse(new TextDecoder().decode(contenido));
      if (typeof documento?._id === "string" && documento._id.trim()) {
        return documento;
      }
    } catch {
      // Solo se aceptan archivos JSON que identifiquen un expediente.
    }
    throw new Error("El archivo no contiene un identificador de expediente válido.");
  }

  async function huella(contenido) {
    const hash = await crypto.subtle.digest("SHA-256", contenido);
    return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
  }

  function combinarRegistros(local, servidor, campo) {
    const previos = local[campo] ?? [];
    const actuales = servidor[campo] ?? [];
    if (!Array.isArray(previos) || !Array.isArray(actuales)) {
      throw new Error("Revisa los registros del archivo original antes de actualizarlo.");
    }
    const ids = new Set(actuales.map(registro => registro.id));
    return [...actuales, ...previos.filter(registro => !ids.has(registro?.id))];
  }

  async function leerArchivo(handle) {
    const archivo = await handle.getFile();
    if (archivo.size > limiteBytes) {
      throw new Error("El archivo supera el tamaño admitido.");
    }
    return { archivo, contenido: await archivo.arrayBuffer() };
  }

  async function elegirArchivo() {
    const [handle] = await window.showOpenFilePicker({
      multiple: false,
      excludeAcceptAllOption: true,
      types: [{ description: "Expediente de MediSpace", accept: { "application/json": [".json"] } }],
    });
    const { archivo, contenido } = await leerArchivo(handle);
    return {
      archivo, handle, expedienteId: leerDocumento(contenido)._id.trim(), huella: await huella(contenido),
    };
  }

  async function permisoEscritura(handle) {
    if (await handle.queryPermission(escritura) === "granted") {
      return true;
    }
    try {
      return await handle.requestPermission(escritura) === "granted";
    } catch (error) {
      // Algunos navegadores requieren un segundo clic tras cerrar el selector.
      if (error.name !== "SecurityError") throw error;
      return false;
    }
  }

  async function vincular({ handle, expedienteId, huella: hash }) {
    const enlace = { handle, expedienteId, huella: hash };
    const clave = sessionStorage.getItem(storageKey) || crypto.randomUUID();
    await archivos("readwrite", almacen => almacen.put(enlace, clave));
    sessionStorage.setItem(storageKey, clave);
    return enlace;
  }

  function prepararFormulario() {
    const formulario = document.getElementById("auth-form");
    const input = document.getElementById("expediente");
    const boton = document.getElementById("elegir-expediente-local");
    const estado = document.getElementById("estado-expediente-local");
    if (!input) {
      formulario.addEventListener("submit", () => sessionStorage.removeItem(storageKey));
      return;
    }

    const mostrar = mensaje => {
      estado.hidden = false;
      estado.textContent = mensaje;
    };
    formulario.addEventListener("submit", evento => {
      if (!input.files.length) {
        evento.preventDefault();
        mostrar("Elige tu archivo JSON para continuar.");
        boton.focus();
      }
    });
    boton.hidden = false;
    const enviar = document.getElementById("btn-auth-submit");
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      enviar.disabled = true;
      try {
        const seleccion = await elegirArchivo();
        const autorizado = await permisoEscritura(seleccion.handle);
        const carga = new DataTransfer();
        carga.items.add(seleccion.archivo);
        await vincular(seleccion);
        input.files = carga.files;
        mostrar(autorizado
          ? `Archivo vinculado: ${seleccion.archivo.name}.`
          : "Archivo seleccionado. Podrás autorizar la escritura desde Resultados.");
      } catch (error) {
        if (error.name !== "AbortError") mostrar(error.message || "No se pudo vincular el archivo.");
      } finally {
        boton.disabled = false;
        enviar.disabled = false;
      }
    });
  }

  async function prepararResultados(panel) {
    const estado = document.getElementById("estado-archivo-local");
    const vincularBoton = document.getElementById("vincular-archivo-local");
    const guardarBoton = document.getElementById("guardar-archivo-local");
    const { expedienteId, url, auto } = panel.dataset;
    const mostrar = mensaje => { estado.textContent = mensaje; };
    panel.hidden = false;
    if (!soportado) {
      mostrar("Para actualizar el archivo original desde la página, abre MediSpace en Chrome o Edge.");
      return;
    }

    const clave = sessionStorage.getItem(storageKey);
    const previo = clave ? await archivos("readonly", almacen => almacen.get(clave)) : null;
    let enlace = previo?.expedienteId === expedienteId ? previo : null;
    guardarBoton.hidden = !enlace;
    vincularBoton.hidden = false;
    mostrar(enlace ? `Archivo vinculado: ${enlace.handle.name}.` : "Vincula el archivo que subiste para actualizarlo.");

    async function guardar() {
      if (await enlace.handle.queryPermission(escritura) !== "granted") {
        mostrar("Pulsa «Actualizar archivo original» para autorizar la escritura.");
        return;
      }
      await navigator.locks.request(`medispace-expediente-${expedienteId}`, async () => {
        const claveActual = sessionStorage.getItem(storageKey);
        const guardado = await archivos("readonly", almacen => almacen.get(claveActual));
        if (!guardado || guardado.expedienteId !== expedienteId) {
          throw new Error("Vuelve a vincular el archivo de este expediente.");
        }
        const respuesta = await fetch(url, { cache: "no-store", redirect: "error" });
        if (!respuesta.ok || !respuesta.headers.get("Content-Type")?.includes("application/json")) {
          throw new Error("No se pudo obtener el expediente. Comprueba tu sesión.");
        }
        const servidor = leerDocumento(await respuesta.arrayBuffer());
        const { contenido } = await leerArchivo(guardado.handle);
        const local = leerDocumento(contenido);
        if (servidor._id.trim() !== expedienteId || local._id.trim() !== expedienteId) {
          throw new Error("El archivo seleccionado pertenece a otro expediente.");
        }
        const combinado = { ...local, chequeos: combinarRegistros(local, servidor, "chequeos") };
        for (const campo of ["diario_psicologico", "semanal_psicologico"]) {
          if (campo in servidor || campo in local) {
            combinado[campo] = combinarRegistros(local, servidor, campo);
          }
        }
        const actualizado = new TextEncoder().encode(JSON.stringify(combinado, null, 2) + "\n");
        const hash = await huella(actualizado);
        const hashLocal = await huella(contenido);
        if (hashLocal !== hash && hashLocal !== guardado.huella) {
          throw new Error("El archivo cambió fuera de MediSpace. Revísalo y vuelve a vincularlo para actualizarlo.");
        }
        if (hashLocal !== hash) {
          const flujo = await guardado.handle.createWritable({ mode: "exclusive" });
          try {
            await flujo.write(actualizado);
            await flujo.close();
          } catch (error) {
            await flujo.abort().catch(() => {});
            throw error;
          }
          await archivos("readwrite", almacen => almacen.put({ ...guardado, huella: hash }, claveActual));
        }
        mostrar(`Archivo original actualizado: ${guardado.handle.name}.`);
      });
    }

    async function ejecutar(operacion) {
      guardarBoton.disabled = true;
      vincularBoton.disabled = true;
      try {
        await operacion();
      } catch (error) {
        if (error.name !== "AbortError") mostrar(error.message || "No se pudo actualizar el archivo original.");
      } finally {
        guardarBoton.disabled = false;
        vincularBoton.disabled = false;
      }
    }

    guardarBoton.addEventListener("click", () => ejecutar(async () => {
      if (await permisoEscritura(enlace.handle)) {
        await guardar();
      } else {
        mostrar("Permite la escritura en el navegador para actualizar este archivo.");
      }
    }));
    vincularBoton.addEventListener("click", () => ejecutar(async () => {
      const seleccion = await elegirArchivo();
      if (seleccion.expedienteId !== expedienteId) {
        throw new Error("El archivo seleccionado pertenece a otro expediente.");
      }
      const autorizado = await permisoEscritura(seleccion.handle);
      enlace = await vincular(seleccion);
      guardarBoton.hidden = false;
      if (autorizado) {
        await guardar();
      } else {
        mostrar("Pulsa «Actualizar archivo original» para autorizar la escritura.");
      }
    }));
    if (enlace && auto === "1") await ejecutar(guardar);
  }

  if (soportado && document.getElementById("auth-form")) prepararFormulario();
  else if (document.getElementById("expediente")) {
    const estado = document.getElementById("estado-expediente-local");
    estado.hidden = false;
    estado.textContent = "Abre MediSpace en Chrome o Edge para elegir y actualizar tu archivo JSON.";
    document.getElementById("btn-auth-submit").disabled = true;
  }
  const panel = document.getElementById("archivo-local");
  if (panel) prepararResultados(panel).catch(() => {
    document.getElementById("estado-archivo-local").textContent = "El navegador no pudo recuperar el archivo vinculado.";
  });
})();
