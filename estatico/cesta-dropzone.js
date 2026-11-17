/* cesta-dropzone.js — upload "arremesse o arquivo na cesta". JS puro, sem dependências, funciona offline (file://).
   Uso: const c = new CestaDropzone(elemento, { titulo, sub, aceitar:'audio/*,video/*', multiplos:true,
          upload:(file, progresso)=>Promise, onArquivos:(files)=>{}, tema:'auto' });
   Arrastar um arquivo do computador para a zona também funciona (e o clique abre o seletor).
   Mira: arraste o ícone do arquivo PARA TRÁS (estilingue) e solte; a trajetória pontilhada mostra o arremesso. */
(function (global) {
  'use strict';
  const G = 1500; // px/s²
  const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
  const ext = (n) => ((n.split('.').pop() || 'arq').slice(0, 4));
  const fmt = (b) => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
  const reduz = () => global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Resolve o arremesso: dado ponto de partida S, alvo T e a direção puxada, devolve velocidade que
     faz a parábola passar por T (assistência de mira). null se o ângulo é inviável. */
  function resolver(S, T, puxe) {
    const dx = T.x - S.x, dir = Math.sign(dx) || 1, D = Math.abs(dx), H = S.y - T.y; // H>0: alvo acima
    if (puxe.y >= 0 || Math.sign(puxe.x) !== dir) return null;               // tem que puxar para baixo e do lado oposto
    const th = Math.atan(-puxe.y / Math.abs(puxe.x));
    if (th < 0.35 || th > 1.4) return null;                                  // ~20° a ~80°
    const den = 2 * Math.cos(th) ** 2 * (D * Math.tan(th) - H);
    if (den <= 0) return null;
    const v = Math.sqrt(G * D * D / den), t = D / (v * Math.cos(th));
    return { v, th, dir, T: t };
  }
  const pos = (S, s, t) => ({ x: S.x + s.dir * s.v * Math.cos(s.th) * t, y: S.y - s.v * Math.sin(s.th) * t + 0.5 * G * t * t });

  function Cesta(raiz, opt) {
    this.o = Object.assign({ titulo: 'Enviar arquivos', sub: 'Arraste e solte, ou arremesse na cesta.', aceitar: '', multiplos: true, tema: 'auto',
      upload: null, onArquivos: null, textoZona: 'Solte os arquivos aqui', textoZona2: 'ou arremesse' }, opt || {});
    this.fila = []; this.enviados = 0; this.ocupado = false; this.mira = null;
    this._montar(raiz);
  }
  const P = Cesta.prototype;

  P._montar = function (raiz) {
    const o = this.o, r = this.r = el('div', 'cesta'); r.dataset.tema = o.tema;
    r.innerHTML =
      '<div class="cesta-topo"><div><h3 class="cesta-titulo"></h3><p class="cesta-sub"></p></div>' +
      '<div class="cesta-cont">Enviados <b>0</b></div></div>' +
      '<div class="cesta-palco"><div class="cesta-zona" tabindex="0" role="button">' +
      '<svg class="up" viewBox="0 0 24 24"><path d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '<strong></strong><span></span></div>' +
      '<div class="cesta-aro"><svg viewBox="0 0 170 150" aria-hidden="true">' +
      '<rect x="46" y="0" width="78" height="52" rx="2" fill="none" stroke="#e8622c" stroke-width="3"/>' +
      '<rect x="78" y="48" width="14" height="8" fill="#e8622c"/>' +
      '<g class="cesta-rede" stroke="#b9bfca" stroke-width="2" fill="none"><path d="M24 62 L56 142 M44 66 L66 142 M64 68 L76 142 M85 69 L85 142 M106 68 L94 142 M126 66 L104 142 M146 62 L114 142"/><path d="M30 80 Q85 92 140 80 M38 100 Q85 112 132 100 M46 120 Q85 130 124 120"/></g>' +
      '<ellipse cx="85" cy="60" rx="64" ry="9" fill="none" stroke="#e8622c" stroke-width="5"/></svg></div>' +
      '<div class="cesta-pontos"></div><div class="cesta-msg" role="status" aria-live="polite"></div>' +
      '<button type="button" class="cesta-lancar" hidden>Lançar</button></div><div class="cesta-lista"></div>';
    r.querySelector('.cesta-titulo').textContent = o.titulo;
    r.querySelector('.cesta-sub').textContent = o.sub;
    r.querySelector('.cesta-zona strong').textContent = o.textoZona;
    r.querySelector('.cesta-zona span').textContent = o.textoZona2;
    raiz.appendChild(r);
    this.q = (s) => r.querySelector(s);
    this.palco = this.q('.cesta-palco'); this.zona = this.q('.cesta-zona'); this.aro = this.q('.cesta-aro');
    this.pontos = this.q('.cesta-pontos'); this.msg = this.q('.cesta-msg'); this.btn = this.q('.cesta-lancar');
    this.input = el('input'); this.input.type = 'file'; this.input.hidden = true; this.input.multiple = !!o.multiplos;
    if (o.aceitar) this.input.accept = o.aceitar; r.appendChild(this.input);
    this.input.addEventListener('change', () => { this.adicionar([...this.input.files]); this.input.value = ''; });
    this.zona.addEventListener('click', () => this.input.click());
    this.zona.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.input.click(); } });
    ['dragenter', 'dragover'].forEach((t) => r.addEventListener(t, (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { e.preventDefault(); this.zona.classList.add('quente'); } }));
    ['dragleave', 'drop'].forEach((t) => r.addEventListener(t, () => this.zona.classList.remove('quente')));
    r.addEventListener('drop', (e) => { e.preventDefault(); const f = [...(e.dataTransfer.files || [])]; if (f.length) this._aceitarDireto(f); });
    this.btn.addEventListener('click', () => this._lancarAuto());
    global.addEventListener('pointermove', (e) => this._mover(e));
    global.addEventListener('pointerup', (e) => this._soltar(e));
    global.addEventListener('pointercancel', () => this._cancelar());
  };

  P._geo = function () {
    const p = this.palco.getBoundingClientRect(), a = this.aro.getBoundingClientRect();
    const svg = this.aro.querySelector('svg').getBoundingClientRect();
    const T = { x: svg.left - p.left + svg.width / 2, y: svg.top - p.top + svg.height * 0.4 };   // centro do aro
    const S = { x: Math.max(48, p.width * 0.14), y: p.height - 70 };
    return { p, T, S };
  };
  P._dizer = function (t) { this.msg.textContent = t || ''; };

  P.adicionar = function (files) {
    const lim = this.o.multiplos ? files : files.slice(0, 1);
    this.fila.push(...lim); this.o.onArquivos && this.o.onArquivos(lim);
    this._chip();
  };
  P._chip = function () {
    if (this.chip) this.chip.remove();
    this.btn.hidden = !this.fila.length;
    if (!this.fila.length) { this.chip = null; this._dizer(''); return; }
    const f = this.fila[0], c = this.chip = el('div', 'cesta-chip'); c.tabIndex = 0; c.setAttribute('role', 'button');
    c.setAttribute('aria-label', 'Arquivo ' + f.name + '. Arraste para trás e solte para arremessar, ou aperte Enter.');
    c.innerHTML = '<div class="cesta-doc"><i></i></div><span class="cesta-nome"></span>';
    c.querySelector('i').textContent = ext(f.name); c.querySelector('.cesta-nome').textContent = f.name;
    if (this.fila.length > 1) c.querySelector('.cesta-doc').appendChild(el('span', 'cesta-mais', '+' + (this.fila.length - 1)));
    const g = this._geo(); this.S = g.S; this._pos(c, g.S);
    c.addEventListener('pointerdown', (e) => this._pegar(e)); c.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); this._lancarAuto(); } });
    this.palco.appendChild(c); this._dizer('Puxe o arquivo para trás e solte.');
  };
  P._pos = function (c, p, rot, esc) { c.style.left = (p.x - 32) + 'px'; c.style.top = (p.y - 29) + 'px'; c.style.transform = 'rotate(' + (rot || 0) + 'deg) scale(' + (esc == null ? 1 : esc) + ')'; };

  P._pegar = function (e) {
    if (this.ocupado || !this.chip) return; e.preventDefault();
    this.mira = { id: e.pointerId }; this.chip.classList.add('arrastando'); try { this.chip.setPointerCapture(e.pointerId); } catch (_) {}
  };
  P._ptLocal = function (e) { const p = this.palco.getBoundingClientRect(); return { x: e.clientX - p.left, y: e.clientY - p.top }; };
  P._mover = function (e) {
    if (!this.mira || e.pointerId !== this.mira.id) return;
    const g = this._geo(), S = g.S, m = this._ptLocal(e);
    let pv = { x: S.x - m.x, y: S.y - m.y }, len = Math.hypot(pv.x, pv.y), max = 110;
    if (len > max) { m.x = S.x - pv.x / len * max; m.y = S.y - pv.y / len * max; pv = { x: S.x - m.x, y: S.y - m.y }; len = max; }
    this._pos(this.chip, m, 0, 1.04); this.mira.pv = pv; this.mira.len = len;
    this.mira.sol = len >= 24 ? resolver(S, g.T, pv) : null; this._pintar(S, this.mira.sol);
  };
  P._pintar = function (S, sol) {
    this.pontos.innerHTML = ''; if (!sol) return;
    for (let t = 0.04; t < sol.T * 0.96; t += 0.045) { const p = pos(S, sol, t), d = el('i', 'cesta-ponto'); d.style.left = p.x + 'px'; d.style.top = p.y + 'px'; d.style.opacity = String(0.35 + 0.5 * (t / sol.T)); this.pontos.appendChild(d); }
  };
  P._cancelar = function () { if (!this.mira) return; this.mira = null; if (this.chip) { this.chip.classList.remove('arrastando'); this._pos(this.chip, this.S); } this.pontos.innerHTML = ''; };
  P._soltar = function (e) {
    if (!this.mira || e.pointerId !== this.mira.id) return;
    const m = this.mira; this.mira = null; this.chip.classList.remove('arrastando'); this.pontos.innerHTML = '';
    if (m.sol) this._arremessar(m.sol); else { this._voltar(); if (m.len >= 24) this._dizer('Errou o ângulo: puxe para trás e para baixo, na direção oposta à cesta.'); }
  };
  P._voltar = function () { const c = this.chip; c.style.transition = 'left .25s,top .25s,transform .25s'; this._pos(c, this.S); setTimeout(() => { if (c) c.style.transition = ''; }, 300); };
  P._lancarAuto = function () {
    if (this.ocupado || !this.chip) return; const g = this._geo(), dir = Math.sign(g.T.x - g.S.x) || 1;
    const sol = resolver(g.S, g.T, { x: dir * 60, y: -70 }) || resolver(g.S, g.T, { x: dir * 60, y: -120 });
    sol ? this._arremessar(sol) : this._aceitarTodos();
  };

  P._arremessar = function (sol) {
    this.ocupado = true; const f = this.fila.shift(), c = this.chip, g = this._geo(), S = g.S; this._dizer('');
    const fim = () => { c.remove(); this.chip = null; this.aro.classList.remove('balanca'); void this.aro.offsetWidth; this.aro.classList.add('balanca'); this.zona.classList.add('quente'); setTimeout(() => this.zona.classList.remove('quente'), 450); this._enviar(f); this.ocupado = false; this._chip(); };
    if (reduz()) return fim();
    const t0 = performance.now(), tot = sol.T + 0.32;
    const passo = (now) => {
      const t = Math.min((now - t0) / 1000, tot);
      let p, esc = 1, op = 1;
      if (t <= sol.T) p = pos(S, sol, t); else { const k = (t - sol.T) / 0.32; p = { x: g.T.x + (S.x - g.T.x) * 0 , y: g.T.y + 70 * k }; esc = 1 - 0.35 * k; op = 1 - k; if (!c._dentro) { c._dentro = 1; c.style.zIndex = 1; } }
      this._pos(c, p, t * 360 * sol.dir * 0.9, esc); c.style.opacity = op;
      t < tot ? requestAnimationFrame(passo) : fim();
    };
    requestAnimationFrame(passo);
  };
  P._aceitarDireto = function (files) {
    this.o.onArquivos && this.o.onArquivos(files);
    this.aro.classList.remove('balanca'); void this.aro.offsetWidth; this.aro.classList.add('balanca');
    (this.o.multiplos ? files : files.slice(0, 1)).forEach((f) => this._enviar(f));
  };
  P._aceitarTodos = function () { const fs = this.fila.splice(0); this._chip(); fs.forEach((f) => this._enviar(f)); };

  P._enviar = function (f) {
    const it = el('div', 'cesta-item', '<div class="ic"></div><div class="mid"><div class="nm"></div><div class="tm"></div><div class="cesta-barra"><div></div></div></div><div class="st">Enviando…</div><div class="check"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>');
    it.querySelector('.nm').textContent = f.name; it.querySelector('.tm').textContent = fmt(f.size || 0);
    const bar = it.querySelector('.cesta-barra > div'), st = it.querySelector('.st');
    this.q('.cesta-lista').appendChild(it);
    const prog = (v) => { bar.style.width = Math.round(Math.min(1, v) * 100) + '%'; };
    const ok = () => { prog(1); it.classList.add('ok'); st.textContent = 'Enviado'; const b = this.q('.cesta-cont b'); b.textContent = String(++this.enviados); };
    const erro = (m) => { it.classList.add('erro'); st.textContent = 'Falhou'; this._dizer(String(m || 'Falha no envio')); };
    const up = this.o.upload || ((file, p) => new Promise((res) => { let v = 0; const iv = setInterval(() => { v += 0.12 + Math.random() * 0.15; p(v); if (v >= 1) { clearInterval(iv); res(); } }, 140); }));
    Promise.resolve().then(() => up(f, prog)).then(ok, erro);
  };

  Cesta._resolver = resolver; Cesta._pos = pos;     // exposto para teste
  global.CestaDropzone = Cesta;
  if (typeof module !== 'undefined') module.exports = Cesta;
})(typeof window !== 'undefined' ? window : globalThis);
