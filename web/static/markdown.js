(function () {
  const SAFE_LINK_PROTOCOLS = ['http:', 'https:', 'mailto:'];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, '&#96;');
  }

  function isSafeUrl(rawUrl) {
    const url = String(rawUrl || '').trim();
    if (!url) return false;
    if (url.startsWith('/') || url.startsWith('#')) return true;
    try {
      const parsed = new URL(url, window.location ? window.location.href : 'http://localhost/');
      return SAFE_LINK_PROTOCOLS.includes(parsed.protocol);
    } catch (_error) {
      return false;
    }
  }

  function renderInline(markdown) {
    const tokens = [];
    let text = String(markdown || '');

    text = text.replace(/`([^`\n]+)`/g, (_match, code) => {
      const token = `\u0000CODE${tokens.length}\u0000`;
      tokens.push(`<code>${escapeHtml(code)}</code>`);
      return token;
    });

    text = text.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (_match, label, rawUrl) => {
      const token = `\u0000LINK${tokens.length}\u0000`;
      if (!isSafeUrl(rawUrl)) {
        tokens.push(escapeHtml(label));
      } else {
        const href = escapeAttribute(rawUrl.trim());
        const text = escapeHtml(label);
        tokens.push(`<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`);
      }
      return token;
    });

    let html = escapeHtml(text)
      .replace(/\*\*([^*\n][\s\S]*?[^*\n])\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');

    tokens.forEach((value, index) => {
      html = html
        .replaceAll(escapeHtml(`\u0000CODE${index}\u0000`), value)
        .replaceAll(escapeHtml(`\u0000LINK${index}\u0000`), value);
    });

    return html;
  }

  function renderParagraph(lines) {
    return `<p>${renderInline(lines.join('\n'))}</p>`;
  }

  function renderList(lines, ordered) {
    const tag = ordered ? 'ol' : 'ul';
    const items = lines.map((line) => {
      const text = ordered
        ? line.replace(/^\s*\d+\.\s+/, '')
        : line.replace(/^\s*[-*]\s+/, '');
      return `<li>${renderInline(text)}</li>`;
    });
    return `<${tag}>${items.join('')}</${tag}>`;
  }

  function renderCodeBlock(code, language) {
    const lang = String(language || '').trim().replace(/[^\w-]/g, '');
    const className = lang ? ` class="language-${escapeAttribute(lang)}"` : '';
    return `<pre><code${className}>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`;
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let paragraph = [];
    let list = [];
    let listOrdered = false;
    let inCode = false;
    let codeLanguage = '';
    let codeLines = [];

    function flushParagraph() {
      if (paragraph.length > 0) {
        blocks.push(renderParagraph(paragraph));
        paragraph = [];
      }
    }

    function flushList() {
      if (list.length > 0) {
        blocks.push(renderList(list, listOrdered));
        list = [];
      }
    }

    for (const line of lines) {
      const fence = line.match(/^\s*```([\w-]*)\s*$/);
      if (fence) {
        if (inCode) {
          blocks.push(renderCodeBlock(codeLines.join('\n'), codeLanguage));
          inCode = false;
          codeLanguage = '';
          codeLines = [];
        } else {
          flushParagraph();
          flushList();
          inCode = true;
          codeLanguage = fence[1] || '';
          codeLines = [];
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      if (/^\s*$/.test(line)) {
        flushParagraph();
        flushList();
        continue;
      }

      const unordered = /^\s*[-*]\s+/.test(line);
      const ordered = /^\s*\d+\.\s+/.test(line);
      if (unordered || ordered) {
        flushParagraph();
        if (list.length > 0 && listOrdered !== ordered) {
          flushList();
        }
        listOrdered = ordered;
        list.push(line);
        continue;
      }

      flushList();
      const heading = line.match(/^\s{0,3}(#{1,4})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        const level = Math.min(heading[1].length + 2, 6);
        blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      } else {
        paragraph.push(line);
      }
    }

    if (inCode) {
      blocks.push(renderCodeBlock(codeLines.join('\n'), codeLanguage));
    }
    flushParagraph();
    flushList();

    return blocks.join('');
  }

  window.MyAgentMarkdown = {
    render: renderMarkdown,
    escapeHtml,
    isSafeUrl,
  };
})();
