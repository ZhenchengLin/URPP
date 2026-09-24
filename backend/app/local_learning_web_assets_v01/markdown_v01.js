"use strict";

// Deliberately bounded Markdown renderer for untrusted chat messages.
// Never parses user HTML, loads remote scripts, or creates untrusted links.
// $...$ and $$...$$ are shown as TeX source, NOT mathematically typeset.
(function () {
  const MAX_MESSAGE_CHARS = 20000;
  const MARK = /(\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\n]+\*|_[^_\n]+_)/g;

  function element(tag, value, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }

  function inline(target, value) {
    let start = 0;
    for (const found of value.matchAll(MARK)) {
      const token = found[0];
      if (found.index > start) target.append(document.createTextNode(value.slice(start, found.index)));
      let item;
      if (token.startsWith("$$")) {
        item = element("code", token.slice(2, -2), "md-tex md-tex-inline");
      } else if (token.startsWith("$")) {
        item = element("code", token.slice(1, -1), "md-tex md-tex-inline");
      } else if (token.startsWith("**") || token.startsWith("__")) {
        item = element("strong", token.slice(2, -2));
      } else if (token.startsWith("`")) {
        item = element("code", token.slice(1, -1));
      } else {
        item = element("em", token.slice(1, -1));
      }
      target.append(item);
      start = found.index + token.length;
    }
    if (start < value.length) target.append(document.createTextNode(value.slice(start)));
  }

  function blockKind(line) {
    if (/^\s*$/.test(line)) return "blank";
    if (/^\s{0,3}(`{3,}|~{3,})/.test(line)) return "fence";
    if (/^\s{0,3}\$\$\s*$/.test(line)) return "math";
    if (/^\s{0,3}#{1,4}\s+/.test(line)) return "heading";
    if (/^\s{0,3}>\s?/.test(line)) return "quote";
    if (/^\s{0,3}[-*+]\s+/.test(line)) return "bullet";
    if (/^\s{0,3}\d{1,3}[.)]\s+/.test(line)) return "number";
    if (/^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) return "rule";
    return "paragraph";
  }

  function renderInto(target, raw) {
    if (!target || typeof target.replaceChildren !== "function") {
      throw new TypeError("Markdown target must be a DOM Element.");
    }
    if (typeof raw !== "string" || raw.length > MAX_MESSAGE_CHARS) {
      throw new TypeError("Markdown message must be a bounded string.");
    }
    target.replaceChildren();
    target.classList.add("md-body");
    const lines = raw.replace(/\r\n?/g, "\n").split("\n");
    let pos = 0;
    while (pos < lines.length) {
      const line = lines[pos];
      const kind = blockKind(line);
      if (kind === "blank") { pos++; continue; }

      if (kind === "fence") {
        const opening = /^\s{0,3}(`{3,}|~{3,})/.exec(line)[1];
        const content = [];
        pos++;
        while (pos < lines.length) {
          const candidate = lines[pos];
          if (new RegExp("^\\s{0,3}" + opening[0] + "{" + opening.length + ",}\\s*$").test(candidate)) {
            pos++;
            break;
          }
          content.push(candidate);
          pos++;
        }
        const pre = element("pre", undefined, "md-code-block");
        pre.append(element("code", content.join("\n")));
        target.append(pre);
        continue;
      }

      if (kind === "math") {
        const content = [];
        pos++;
        while (pos < lines.length && !/^\s{0,3}\$\$\s*$/.test(lines[pos])) {
          content.push(lines[pos]); pos++;
        }
        if (pos < lines.length) pos++;
        const pre = element("pre", undefined, "md-tex-block");
        pre.append(element("code", content.join("\n")));
        target.append(pre);
        continue;
      }

      if (kind === "heading") {
        const match = /^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$/.exec(line);
        const heading = element(match[1].length < 3 ? "h4" : "h5", undefined, "md-heading");
        inline(heading, match[2]); target.append(heading); pos++;
        continue;
      }

      if (kind === "rule") { target.append(element("hr")); pos++; continue; }

      if (kind === "quote") {
        const content = [];
        while (pos < lines.length && blockKind(lines[pos]) === "quote") {
          content.push(lines[pos].replace(/^\s{0,3}>\s?/, "")); pos++;
        }
        const quote = element("blockquote");
        const p = element("p"); inline(p, content.join("\n")); quote.append(p);
        target.append(quote); continue;
      }

      if (kind === "bullet" || kind === "number") {
        const list = element(kind === "bullet" ? "ul" : "ol");
        const pattern = kind === "bullet" ? /^\s{0,3}[-*+]\s+(.+)$/ : /^\s{0,3}\d{1,3}[.)]\s+(.+)$/;
        while (pos < lines.length && blockKind(lines[pos]) === kind) {
          const li = element("li"); inline(li, pattern.exec(lines[pos])[1]);
          list.append(li); pos++;
        }
        target.append(list); continue;
      }

      const content = [];
      while (pos < lines.length && blockKind(lines[pos]) === "paragraph") {
        content.push(lines[pos]); pos++;
      }
      const paragraph = element("p");
      inline(paragraph, content.join("\n"));
      target.append(paragraph);
    }
  }

  globalThis.URPPMarkdownV01 = Object.freeze({ renderInto });
}());
