// ==UserScript==
// @name         FanFiction.net Story Exporter
// @namespace    book-converter
// @version      1.0
// @description  Passively captures each fanfiction.net chapter page's HTML as you read it and lets you export the whole story as one JSON file, in the exact shape FfNetEbookRepository/FfNetHtmlConverter already expect - no automated bulk fetching, so it never trips the same Cloudflare rate limit that book-converter's own scraper hits on long stories. Just browse the story chapter-by-chapter like normal (click "Next" / pick from the dropdown) with this script active, then hit Export once every chapter shows captured.
// @match        https://www.fanfiction.net/s/*
// @match        https://www.fanfiction.net/r/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const TAG = '[ffnet exporter]';
  const log = (...args) => console.log(TAG, ...args);
  const warn = (...args) => console.warn(TAG, ...args);

  // fanfiction.net's chapter navigation is a plain full-page reload (the
  // <select id=chap_select> does `self.location = ...` on change, no SPA
  // routing), so "browse normally" naturally gives this script one full
  // page load per chapter - that's the hook point. No XHR/fetch capture
  // needed, unlike the OverDrive script next to this one.
  const STORY_ID_RE = /\/s\/(\d+)\//;
  const storyIdMatch = location.pathname.match(STORY_ID_RE);
  if (!storyIdMatch) {
    log('no story id in URL, not a story page - skipping', location.pathname);
    return;
  }
  const storyId = storyIdMatch[1];
  const storageKey = `ffnet-export:${storyId}`;

  function parseChapterList() {
    const select = document.getElementById('chap_select');
    if (!select) {
      // Single-chapter stories don't render the dropdown at all.
      return [{ number: 1, title: document.title || '' }];
    }
    return Array.from(select.options).map((opt) => ({
      number: parseInt(opt.value, 10),
      title: (opt.textContent || '').replace(/^\d+\.\s*/, '').trim(),
    }));
  }

  function currentChapterNumber(chapterList) {
    const select = document.getElementById('chap_select');
    if (select) return parseInt(select.value, 10);
    // No dropdown means a one-shot; the URL's chapter segment is 1 if
    // present, otherwise this is the only chapter there is.
    const m = location.pathname.match(/\/s\/\d+\/(\d+)\//);
    return m ? parseInt(m[1], 10) : chapterList[0].number;
  }

  function storyTitle() {
    const heading = document.querySelector('#profile_top b.xcontrast_txt');
    return (heading?.textContent || document.title || 'untitled').trim();
  }

  // Cloudflare sometimes interstitials a chapter navigation instead of
  // serving the real page - same "Just a moment..." challenge the Python
  // scraper hits (see ffnet_repository.py's _has_story_content). Capturing
  // that page's HTML as if it were the chapter would silently poison the
  // export with a challenge page marked "captured", with no easy way to
  // tell later. Treat anything without real story markup as blocked
  // instead of capturing it.
  function isBlockedPage() {
    if (document.title.includes('Just a moment')) return true;
    if (document.querySelector('#challenge-error-text, script[src*="challenges.cloudflare.com"]')) {
      return true;
    }
    // A real chapter page always has #storytext; a real story page always
    // has #profile_top. Missing both means this isn't the page we think it is.
    return !document.getElementById('storytext') && !document.getElementById('profile_top');
  }

  function loadBundle() {
    const raw = GM_getValue(storageKey, null);
    if (!raw) return { storyId, title: storyTitle(), chapters: {} };
    try {
      return JSON.parse(raw);
    } catch (e) {
      warn('stored bundle was corrupt, starting fresh', e);
      return { storyId, title: storyTitle(), chapters: {} };
    }
  }

  function saveBundle(bundle) {
    GM_setValue(storageKey, JSON.stringify(bundle));
  }

  function slugify(text) {
    return (
      (text || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'ffnet-story'
    );
  }

  function exportBundle(bundle, chapterList) {
    const chapters = chapterList
      .map((c) => c.number)
      .sort((a, b) => a - b)
      .filter((n) => bundle.chapters[n] != null)
      .map((n) => ({ number: n, html: bundle.chapters[n] }));
    // Matches ffnet_repository.py's `_encode(payload)` output exactly -
    // FfNetEbookRepository loads a local .json file with this shape
    // directly instead of hitting the network (see that file's
    // `_load_local_export` check).
    const payload = { story_id: bundle.storyId, chapters };
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${slugify(bundle.title)}-${bundle.storyId}.ffnet.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    log('exported', chapters.length, 'chapters to', a.download);
  }

  function basePanel() {
    document.getElementById('ffnet-exporter-panel')?.remove();
    const panel = document.createElement('div');
    panel.id = 'ffnet-exporter-panel';
    Object.assign(panel.style, {
      position: 'fixed',
      top: '12px',
      right: '12px',
      zIndex: 2147483647,
      background: '#1e1e1e',
      color: '#eee',
      border: '1px solid #444',
      borderRadius: '8px',
      padding: '10px 12px',
      fontFamily: 'sans-serif',
      fontSize: '13px',
      maxWidth: '260px',
      boxShadow: '0 2px 8px rgba(0,0,0,.4)',
    });
    return panel;
  }

  function buildBlockedPanel() {
    const panel = basePanel();
    panel.innerHTML = `
      <div style="font-weight:600;margin-bottom:4px;">FF.net Exporter — story ${storyId}</div>
      <div style="color:#f88;margin-bottom:6px;">⚠ This looks like a Cloudflare challenge page, not the real chapter — nothing captured.</div>
      <div style="opacity:.85;">Wait a bit and reload. Existing captured chapters are untouched.</div>
    `;
    document.body.appendChild(panel);
  }

  function buildPanel(bundle, chapterList, capturedThisLoad) {
    const capturedCount = chapterList.filter((c) => bundle.chapters[c.number] != null).length;
    const missing = chapterList.filter((c) => bundle.chapters[c.number] == null);

    const panel = basePanel();

    const status = capturedThisLoad
      ? `Captured chapter ${capturedThisLoad} ✓`
      : 'This chapter already captured';
    panel.innerHTML = `
      <div style="font-weight:600;margin-bottom:4px;">FF.net Exporter — story ${bundle.storyId}</div>
      <div style="opacity:.85;margin-bottom:6px;">${status}</div>
      <div style="margin-bottom:8px;">${capturedCount} / ${chapterList.length} chapters captured</div>
    `;

    if (missing.length) {
      const list = document.createElement('div');
      Object.assign(list.style, {
        maxHeight: '140px',
        overflowY: 'auto',
        marginBottom: '8px',
        borderTop: '1px solid #444',
        paddingTop: '6px',
      });
      list.innerHTML =
        '<div style="opacity:.7;margin-bottom:4px;">Still missing:</div>' +
        missing
          .map(
            (c) =>
              `<a href="/s/${storyId}/${c.number}/" style="display:block;color:#6cf;text-decoration:none;padding:1px 0;">${c.number}. ${c.title || ''}</a>`
          )
          .join('');
      panel.appendChild(list);
    }

    const btnRow = document.createElement('div');
    btnRow.style.display = 'flex';
    btnRow.style.gap = '6px';

    const exportBtn = document.createElement('button');
    exportBtn.textContent = missing.length ? `Export (${missing.length} missing)` : 'Export ✓';
    Object.assign(exportBtn.style, {
      flex: '1',
      padding: '6px 8px',
      background: missing.length ? '#555' : '#1a7f37',
      color: '#fff',
      border: 'none',
      borderRadius: '5px',
      cursor: 'pointer',
    });
    exportBtn.addEventListener('click', () => exportBundle(bundle, chapterList));
    btnRow.appendChild(exportBtn);

    const clearBtn = document.createElement('button');
    clearBtn.textContent = 'Clear';
    Object.assign(clearBtn.style, {
      padding: '6px 8px',
      background: '#7a1f1f',
      color: '#fff',
      border: 'none',
      borderRadius: '5px',
      cursor: 'pointer',
    });
    clearBtn.addEventListener('click', () => {
      if (!confirm(`Clear ${capturedCount} captured chapter(s) for story ${storyId}?`)) return;
      GM_deleteValue(storageKey);
      log('cleared bundle for story', storyId);
      location.reload();
    });
    btnRow.appendChild(clearBtn);

    panel.appendChild(btnRow);
    document.body.appendChild(panel);
  }

  function run() {
    if (isBlockedPage()) {
      warn('Cloudflare challenge (or unrecognized page) detected - not capturing', location.href);
      buildBlockedPanel();
      return;
    }

    const chapterList = parseChapterList();
    const chapterNumber = currentChapterNumber(chapterList);
    const bundle = loadBundle();
    bundle.title = storyTitle();

    let capturedThisLoad = null;
    if (bundle.chapters[chapterNumber] == null) {
      bundle.chapters[chapterNumber] = document.documentElement.outerHTML;
      saveBundle(bundle);
      capturedThisLoad = chapterNumber;
      log('captured chapter', chapterNumber, 'of story', storyId);
    } else {
      log('chapter', chapterNumber, 'already captured, leaving as-is');
    }

    buildPanel(bundle, chapterList, capturedThisLoad);
  }

  run();
})();
