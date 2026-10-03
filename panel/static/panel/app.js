// Comportamiento general del panel (menú móvil, filas clicables, confirmaciones).
(function () {
  "use strict";

  // Menú lateral en móvil
  var abrir = document.getElementById("abrir-menu");
  if (abrir) {
    abrir.addEventListener("click", function () { document.body.classList.add("menu-abierto"); });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("menu-abierto") &&
          !e.target.closest("#sidebar") && !e.target.closest("#abrir-menu")) {
        document.body.classList.remove("menu-abierto");
      }
    });
  }

  // Filas de tabla que navegan al detalle (sin romper los enlaces internos)
  document.querySelectorAll("tr[data-href]").forEach(function (fila) {
    fila.addEventListener("click", function (e) {
      if (e.target.closest("a, button, form, input")) return;
      window.location = fila.dataset.href;
    });
  });

  // Botones que abren un <dialog> de confirmación: data-abrir="id-del-dialog"
  document.querySelectorAll("[data-abrir]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var d = document.getElementById(btn.dataset.abrir);
      if (d && d.showModal) d.showModal();
    });
  });
  document.querySelectorAll("dialog [data-cerrar]").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.closest("dialog").close(); });
  });

  // Evita doble envío: deshabilita el botón al enviar formularios marcados
  document.querySelectorAll("form[data-una-vez]").forEach(function (form) {
    form.addEventListener("submit", function () {
      form.querySelectorAll("button[type=submit]").forEach(function (b) {
        b.disabled = true;
        if (b.dataset.cargando) b.textContent = b.dataset.cargando;
      });
    });
  });
})();

// Validador de RUT en vivo: cualquier <input data-rut> (o name="rut").
// Agrega el guion automáticamente y muestra "RUT válido" / "RUT inválido".
(function () {
  "use strict";

  function limpiar(valor) {
    var l = (valor || "").replace(/[^0-9kK]/g, "").toUpperCase();
    // La K solo puede ser el dígito verificador (último carácter).
    return l.slice(0, -1).replace(/K/g, "") + l.slice(-1);
  }

  function calcularDv(cuerpo) {
    var suma = 0, mult = 2;
    for (var i = cuerpo.length - 1; i >= 0; i--) {
      suma += parseInt(cuerpo.charAt(i), 10) * mult;
      mult = mult === 7 ? 2 : mult + 1;
    }
    var resto = 11 - (suma % 11);
    return resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  }

  function formatear(limpio) {
    return limpio.length < 2 ? limpio : limpio.slice(0, -1) + "-" + limpio.slice(-1);
  }

  function esValido(limpio) {
    if (limpio.length < 8 || limpio.length > 9) return false;
    var cuerpo = limpio.slice(0, -1);
    return /^\d+$/.test(cuerpo) && calcularDv(cuerpo) === limpio.slice(-1);
  }

  function mostrar(input, aviso, completo) {
    var limpio = limpiar(input.value);
    aviso.className = "rut-estado";
    aviso.textContent = "";
    input.classList.remove("rut-ok", "rut-mal");
    if (!limpio) return;
    if (esValido(limpio)) {
      aviso.classList.add("rut-estado--ok");
      aviso.textContent = "✓ RUT válido";
      input.classList.add("rut-ok");
      input.setCustomValidity("");
    } else if (completo || limpio.length >= 8) {
      aviso.classList.add("rut-estado--mal");
      aviso.textContent = "✗ RUT inválido";
      input.classList.add("rut-mal");
      input.setCustomValidity("RUT inválido");
    }
  }

  document.querySelectorAll("input[data-rut], input[name='rut']").forEach(function (input) {
    input.setAttribute("maxlength", "12");
    input.setAttribute("autocomplete", "off");
    var aviso = document.createElement("div");
    aviso.className = "rut-estado";
    aviso.setAttribute("aria-live", "polite");
    input.insertAdjacentElement("afterend", aviso);

    // "Válido" se muestra al instante; "inválido" espera una pausa al escribir,
    // para no marcar error mientras falta el dígito verificador.
    var espera;
    input.addEventListener("input", function () {
      input.value = formatear(limpiar(input.value));
      clearTimeout(espera);
      if (esValido(limpiar(input.value))) {
        mostrar(input, aviso, true);
      } else {
        mostrar(input, aviso, false);
        aviso.className = "rut-estado";
        aviso.textContent = "";
        input.classList.remove("rut-mal");
        espera = setTimeout(function () { mostrar(input, aviso, true); }, 600);
      }
    });
    input.addEventListener("blur", function () { clearTimeout(espera); mostrar(input, aviso, true); });

    if (input.value) {
      input.value = formatear(limpiar(input.value));
      mostrar(input, aviso, true);
    }
  });
})();
