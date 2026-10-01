"use strict";

// URPP local MathJax v3.2.2 SVG configuration. This file must load BEFORE
// the locally hosted MathJax component and the Markdown chat renderer.
// MathJax never receives course files or the Session ID from this adapter.
(function () {
  const MAX_TEX_CHARS = 4096;
  const MAX_FORMULAS_PER_PAGE = 160;
  let attempted = 0;

  // No remote loading, no browser-wide automatic DOM scanning, no web fonts.
  // Keep the TeX package set small (no require, autoload, html, or unicode).
  globalThis.MathJax = {
    startup: {typeset: false},
    tex: {packages: ["base", "ams"], maxBuffer: MAX_TEX_CHARS, maxMacros: 1000},
    svg: {fontCache: "none"},
    options: {enableMenu: false}
  };

  function typeset(target, tex, display) {
    if (!target || typeof target.replaceChildren !== "function" ||
        typeof tex !== "string" || tex.length > MAX_TEX_CHARS ||
        !tex.trim() || typeof display !== "boolean" ||
        ++attempted > MAX_FORMULAS_PER_PAGE) return;

    // Never interpret output or input as HTML. The fallback was inserted by
    // the Markdown renderer using textContent and stays on render failure.
    const fallback = target.firstChild;
    if (!fallback) return;
    const expectedTex = tex;
    const expectedDisplay = display;
    const mathjax = globalThis.MathJax;
    if (!mathjax || !mathjax.startup ||
        !mathjax.startup.promise ||
        typeof mathjax.tex2svgPromise !== "function") return;

    Promise.resolve(mathjax.startup.promise)
      .then(() => mathjax.tex2svgPromise(expectedTex, {display: expectedDisplay}))
      .then((rendered) => {
        // A refreshed conversation may have detached the old message DOM.
        if (!target.isConnected || target.firstChild !== fallback ||
            !rendered || rendered.nodeType !== 1 ||
            !rendered.querySelector || !rendered.querySelector("svg")) return;
        // A TeX parse error remains source text rather than a misleading SVG.
        if (rendered.querySelector("merror, mjx-merror")) return;
        target.replaceChildren(rendered);
      })
      .catch(() => { /* Retain the original, readable TeX fallback. */ });
  }

  globalThis.URPPMathV01 = Object.freeze({typeset});
}());
