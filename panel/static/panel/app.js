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
