// Galaxia animada de la pantalla de ingreso + detalles del formulario.
(function () {
  "use strict";

  var canvas = document.getElementById("galaxia");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Paleta Alto Nivel: celeste, naranjo, turquesa y blanco.
  var COLORES = [
    [61, 191, 232], [61, 191, 232], [61, 191, 232],
    [249, 82, 11], [249, 82, 11],
    [24, 160, 170],
    [235, 240, 255],
  ];

  var ancho = 0, alto = 0, dpr = 1;
  var nodos = [], estrellas = [], fugaces = [];
  var raton = { x: -9999, y: -9999, activo: false };
  var DISTANCIA = 150, RADIO_RATON = 190;
  // Con "reducir movimiento" la galaxia sigue viva, pero más lenta y sin estrellas fugaces.
  var VELOCIDAD = reducido ? 0.45 : 1;

  function azar(a, b) { return a + Math.random() * (b - a); }

  function crear() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    var r = canvas.getBoundingClientRect();
    ancho = r.width; alto = r.height;
    canvas.width = Math.round(ancho * dpr);
    canvas.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var area = ancho * alto;
    var cantidad = Math.max(40, Math.min(130, Math.round(area / 11000)));
    nodos = [];
    for (var i = 0; i < cantidad; i++) {
      var c = COLORES[(Math.random() * COLORES.length) | 0];
      nodos.push({
        x: azar(0, ancho), y: azar(0, alto),
        vx: azar(-0.22, 0.22), vy: azar(-0.22, 0.22),
        r: azar(1, 2.6), c: c, fase: azar(0, Math.PI * 2),
      });
    }
    // Fondo de estrellas lejanas (con paralaje leve).
    estrellas = [];
    var n = Math.round(area / 2600);
    for (var j = 0; j < n; j++) {
      estrellas.push({ x: azar(0, ancho), y: azar(0, alto), r: azar(0.2, 1.1), a: azar(0.15, 0.8),
        v: azar(0.004, 0.02), f: azar(0, Math.PI * 2), z: azar(0.2, 1) });
    }
  }

  function lanzarFugaz() {
    var desdeArriba = Math.random() < 0.6;
    fugaces.push({
      x: desdeArriba ? azar(ancho * 0.2, ancho) : ancho + 20,
      y: desdeArriba ? -20 : azar(0, alto * 0.5),
      vx: azar(-9, -6), vy: azar(3, 5), vida: 1,
      c: Math.random() < 0.5 ? [249, 82, 11] : [61, 191, 232],
    });
  }

  var t = 0;
  function cuadro() {
    t += 1;
    ctx.clearRect(0, 0, ancho, alto);

    // Estrellas lejanas que titilan
    var px = raton.activo ? (raton.x - ancho / 2) / ancho : 0;
    var py = raton.activo ? (raton.y - alto / 2) / alto : 0;
    for (var s = 0; s < estrellas.length; s++) {
      var e = estrellas[s];
      var brillo = e.a * (0.55 + 0.45 * Math.sin(e.f + t * e.v));
      ctx.fillStyle = "rgba(220,230,255," + brillo.toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(e.x - px * 18 * e.z, e.y - py * 18 * e.z, e.r, 0, Math.PI * 2);
      ctx.fill();
    }

    // Mover nodos
    for (var i = 0; i < nodos.length; i++) {
      var p = nodos[i];
      if (raton.activo) {
        var dx = raton.x - p.x, dy = raton.y - p.y, d = Math.sqrt(dx * dx + dy * dy);
        if (d < RADIO_RATON && d > 1) {
          var fuerza = (1 - d / RADIO_RATON) * 0.035;
          p.vx += (dx / d) * fuerza;
          p.vy += (dy / d) * fuerza;
        }
      }
      p.vx *= 0.985; p.vy *= 0.985;
      // Velocidad mínima para que nunca se detengan del todo
      var vel = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (vel < 0.12) { p.vx += azar(-0.03, 0.03); p.vy += azar(-0.03, 0.03); }
      if (vel > 1.6) { p.vx *= 0.9; p.vy *= 0.9; }
      p.x += p.vx * VELOCIDAD; p.y += p.vy * VELOCIDAD;
      if (p.x < -20) p.x = ancho + 20; else if (p.x > ancho + 20) p.x = -20;
      if (p.y < -20) p.y = alto + 20; else if (p.y > alto + 20) p.y = -20;
    }

    // Líneas entre nodos cercanos (color mezclado de ambos extremos)
    ctx.lineWidth = 0.8;
    for (var a = 0; a < nodos.length; a++) {
      for (var b = a + 1; b < nodos.length; b++) {
        var n1 = nodos[a], n2 = nodos[b];
        var ddx = n1.x - n2.x, ddy = n1.y - n2.y;
        var dist2 = ddx * ddx + ddy * ddy;
        if (dist2 < DISTANCIA * DISTANCIA) {
          var alfa = (1 - Math.sqrt(dist2) / DISTANCIA) * 0.55;
          var g = ctx.createLinearGradient(n1.x, n1.y, n2.x, n2.y);
          g.addColorStop(0, "rgba(" + n1.c.join(",") + "," + alfa.toFixed(3) + ")");
          g.addColorStop(1, "rgba(" + n2.c.join(",") + "," + alfa.toFixed(3) + ")");
          ctx.strokeStyle = g;
          ctx.beginPath(); ctx.moveTo(n1.x, n1.y); ctx.lineTo(n2.x, n2.y); ctx.stroke();
        }
      }
    }

    // Conexiones con el cursor
    if (raton.activo) {
      for (var k = 0; k < nodos.length; k++) {
        var q = nodos[k];
        var mx = q.x - raton.x, my = q.y - raton.y, md = Math.sqrt(mx * mx + my * my);
        if (md < RADIO_RATON) {
          ctx.strokeStyle = "rgba(249,82,11," + ((1 - md / RADIO_RATON) * 0.7).toFixed(3) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(q.x, q.y); ctx.lineTo(raton.x, raton.y); ctx.stroke();
        }
      }
      var halo = ctx.createRadialGradient(raton.x, raton.y, 0, raton.x, raton.y, 90);
      halo.addColorStop(0, "rgba(249,82,11,0.18)");
      halo.addColorStop(1, "rgba(249,82,11,0)");
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(raton.x, raton.y, 90, 0, Math.PI * 2); ctx.fill();
    }

    // Nodos con resplandor
    for (var m = 0; m < nodos.length; m++) {
      var o = nodos[m];
      var pul = 0.7 + 0.3 * Math.sin(o.fase + t * 0.03);
      var col = o.c.join(",");
      var rg = ctx.createRadialGradient(o.x, o.y, 0, o.x, o.y, o.r * 5);
      rg.addColorStop(0, "rgba(" + col + "," + (0.5 * pul).toFixed(3) + ")");
      rg.addColorStop(1, "rgba(" + col + ",0)");
      ctx.fillStyle = rg;
      ctx.beginPath(); ctx.arc(o.x, o.y, o.r * 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(" + col + "," + (0.95 * pul).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(o.x, o.y, o.r, 0, Math.PI * 2); ctx.fill();
    }

    // Estrellas fugaces
    if (!reducido && Math.random() < 0.004 && fugaces.length < 2) lanzarFugaz();
    for (var f = fugaces.length - 1; f >= 0; f--) {
      var fz = fugaces[f];
      fz.x += fz.vx; fz.y += fz.vy; fz.vida -= 0.012;
      var cola = ctx.createLinearGradient(fz.x, fz.y, fz.x - fz.vx * 14, fz.y - fz.vy * 14);
      cola.addColorStop(0, "rgba(255,255,255," + fz.vida.toFixed(3) + ")");
      cola.addColorStop(0.25, "rgba(" + fz.c.join(",") + "," + (fz.vida * 0.8).toFixed(3) + ")");
      cola.addColorStop(1, "rgba(" + fz.c.join(",") + ",0)");
      ctx.strokeStyle = cola; ctx.lineWidth = 2; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(fz.x, fz.y); ctx.lineTo(fz.x - fz.vx * 14, fz.y - fz.vy * 14); ctx.stroke();
      if (fz.vida <= 0 || fz.x < -200 || fz.y > alto + 200) fugaces.splice(f, 1);
    }

    requestAnimationFrame(cuadro);
  }

  var galaxia = canvas.parentElement;
  galaxia.addEventListener("mousemove", function (ev) {
    var r = canvas.getBoundingClientRect();
    raton.x = ev.clientX - r.left; raton.y = ev.clientY - r.top; raton.activo = true;
  });
  galaxia.addEventListener("mouseleave", function () { raton.activo = false; });
  // La galaxia está detrás del formulario en celular: escuchamos en toda la ventana.
  window.addEventListener("touchmove", function (ev) {
    var r = canvas.getBoundingClientRect(), tt = ev.touches[0];
    raton.x = tt.clientX - r.left; raton.y = tt.clientY - r.top; raton.activo = true;
  }, { passive: true });
  window.addEventListener("touchend", function () { raton.activo = false; });

  var redim;
  window.addEventListener("resize", function () {
    clearTimeout(redim);
    redim = setTimeout(crear, 150);
  });

  crear();
  cuadro();
})();

// Mostrar/ocultar contraseña y estado de carga del botón
(function () {
  "use strict";
  var ojo = document.getElementById("ver-clave");
  var clave = document.getElementById("id_password");
  if (ojo && clave) {
    ojo.addEventListener("click", function () {
      var visible = clave.type === "text";
      clave.type = visible ? "password" : "text";
      ojo.setAttribute("aria-pressed", String(!visible));
      ojo.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
      clave.focus();
    });
  }
  var form = document.querySelector(".acceso__form");
  var boton = document.getElementById("boton-ingresar");
  if (form && boton) {
    form.addEventListener("submit", function () {
      boton.classList.add("cargando");
      boton.querySelector("span").textContent = "Ingresando…";
    });
  }
})();
