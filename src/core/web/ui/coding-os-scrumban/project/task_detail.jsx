// Task detail drawer — renders the task's markdown file (frontmatter + body)
const { useEffect: useEffectTD, useMemo: useMemoTD } = React;

// Tiny, safe markdown renderer tuned for task files (no arbitrary HTML).
function renderMd(md) {
  if (!md) return [];
  const lines = md.split('\n');
  const out = [];
  let i = 0;
  let key = 0;

  const inline = (txt) => {
    // escape, then apply: `code`, **bold**, *em*, images, [text](url), TASK-###
    let safe = txt.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
    safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    safe = safe.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    // image before link, since they share syntax
    safe = safe.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img class="md-img" alt="$1" src="$2" />');
    safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    safe = safe.replace(/\b(TASK-\d{3})\b/g, '<a class="md-tasklink" data-task="$1">$1</a>');
    return <span dangerouslySetInnerHTML={{ __html: safe }} />;
  };

  while (i < lines.length) {
    const line = lines[i];

    // empty
    if (!line.trim()) { i++; continue; }

    // heading
    const h = /^(#{1,4})\s+(.+)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const Tag = `h${level + 1}`; // h1 -> h2 etc, page title is h1
      out.push(<Tag key={key++} className={`md-h md-h${level}`}>{inline(h[2])}</Tag>);
      i++; continue;
    }

    // fenced code
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      out.push(
        <pre key={key++} className="md-pre">
          {lang && <div className="md-lang">{lang}</div>}
          <code>{buf.join('\n')}</code>
        </pre>
      );
      continue;
    }

    // blockquote
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      out.push(<blockquote key={key++} className="md-quote">{inline(buf.join(' '))}</blockquote>);
      continue;
    }

    // GIVEN/WHEN/THEN callout block
    if (/^(GIVEN|WHEN|THEN|AND)\b/.test(line.trim())) {
      const buf = [];
      while (i < lines.length && /^(GIVEN|WHEN|THEN|AND)\b/.test(lines[i].trim())) {
        buf.push(lines[i]); i++;
      }
      out.push(
        <div key={key++} className="md-gwt">
          {buf.map((b, idx) => {
            const m = /^(GIVEN|WHEN|THEN|AND)\s+(.+)$/.exec(b.trim());
            return m ? (
              <div key={idx} className="md-gwt-row">
                <span className={`md-gwt-kw md-gwt-${m[1].toLowerCase()}`}>{m[1]}</span>
                <span>{inline(m[2])}</span>
              </div>
            ) : null;
          })}
        </div>
      );
      continue;
    }

    // list
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i++;
      }
      out.push(
        <ul key={key++} className="md-ul">
          {items.map((it, idx) => {
            // checkbox
            const cb = /^\[([ xX])\]\s+(.+)$/.exec(it);
            if (cb) {
              const done = cb[1].toLowerCase() === 'x';
              return <li key={idx} className={`md-li md-check ${done ? 'done' : ''}`}>
                <span className="md-box">{done ? '✓' : ''}</span>
                {inline(cb[2])}
              </li>;
            }
            return <li key={idx} className="md-li">{inline(it)}</li>;
          })}
        </ul>
      );
      continue;
    }

    // ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push(<ol key={key++} className="md-ol">{items.map((it, idx) => <li key={idx} className="md-li">{inline(it)}</li>)}</ol>);
      continue;
    }

    // horizontal rule
    if (/^---+\s*$/.test(line)) { out.push(<hr key={key++} className="md-hr" />); i++; continue; }

    // paragraph
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !/^(#|```|>|\s*[-*]\s|\s*\d+\.\s|---)/.test(lines[i])) {
      buf.push(lines[i]); i++;
    }
    out.push(<p key={key++} className="md-p">{inline(buf.join(' '))}</p>);
  }
  return out;
}

// Synthesize the markdown file contents from task fixture data.
// This is what the file on disk would look like for each TASK.
function synthesizeTaskMd(task) {
  const fm = {
    id: task.id,
    title: task.title,
    swimlane: task.swimlane,
    kind: task.kind,
    status: task.status,
    priority: task.priority,
    appetite: task.appetite,
    epic: task.epic || null,
    labels: task.labels && task.labels.length ? task.labels : null,
    agent: task.agent || null,
    depends: task.depends && task.depends.length ? task.depends : null,
  };
  const fmLines = ['---'];
  for (const [k, v] of Object.entries(fm)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) fmLines.push(`${k}: [${v.map(x => JSON.stringify(x)).join(', ')}]`);
    else fmLines.push(`${k}: ${typeof v === 'string' && /[:#]/.test(v) ? JSON.stringify(v) : v}`);
  }
  fmLines.push('---', '');

  // Body — generic template
  const body = [];
  body.push(`# ${task.title}`, '');

  body.push('## Outcome', '');
  body.push(task._outcome || taskOutcome(task), '');

  body.push('## Acceptance criteria', '');
  const gwt = taskGwt(task);
  body.push(...gwt, '');

  if (task.depends && task.depends.length) {
    body.push('## Depends on', '');
    body.push(...task.depends.map(d => `- ${d}`), '');
  }

  if (task.blockedReason) {
    body.push('## Blocked', '');
    body.push(`> ${task.blockedReason}`, '');
  }

  body.push('## Work log', '');
  if (task.workLog && task.workLog.length) {
    for (const e of task.workLog) {
      body.push(`### ${e.time} — ${e.agent}`);
      body.push(e.msg, '');
    }
  } else {
    body.push('_No entries yet — `capture-work-log.sh` will append here on first transition._', '');
  }

  body.push('## Notes', '');
  body.push(taskNotes(task), '');

  return fmLines.join('\n') + body.join('\n');
}

function taskOutcome(t) {
  const kindWord = { bug: 'Fix', feature: 'Ship', chore: 'Clean up', spike: 'Investigate', docs: 'Document', refactor: 'Refactor', test: 'Cover', security: 'Harden' }[t.kind] || 'Complete';
  return `${kindWord} \`${t.title.toLowerCase()}\` so the ${t.swimlane} stack stops blocking ${t.epic || 'downstream work'}. Appetite: **${t.appetite}** — ship smaller if we blow past it.`;
}

function taskGwt(t) {
  // Deterministic fake G/W/T per kind
  const rows = {
    bug: [
      `GIVEN the repro case from ${t.id}`,
      `WHEN the fix lands on \`main\``,
      `THEN the failing test passes and no existing tests regress`,
    ],
    feature: [
      `GIVEN an agent or human invokes the new behavior`,
      `WHEN it runs against the phase-L fixtures`,
      `THEN frontmatter validates, hooks fire in order, and the transition is captured in status_history`,
    ],
    chore: [
      `GIVEN the chore is complete`,
      `WHEN CI runs on the PR`,
      `THEN no lint/type/format warnings remain in scope`,
    ],
    spike: [
      `GIVEN the question is framed in the outcome`,
      `WHEN the timebox expires (${t.appetite})`,
      `THEN a decision doc lands in docs/decisions/ with a clear recommendation`,
    ],
    docs: [
      `GIVEN a reader new to ${t.swimlane}`,
      `WHEN they read this doc end to end`,
      `THEN they can answer the three canonical questions without asking in chat`,
    ],
    refactor: [
      `GIVEN the existing behavior covered by tests`,
      `WHEN the refactor lands`,
      `THEN all tests pass unchanged and cyclomatic complexity drops`,
    ],
    test: [
      `GIVEN the uncovered code paths identified in ${t.id}`,
      `WHEN the new tests run`,
      `THEN branch coverage on the target module is ≥ 90%`,
    ],
    security: [
      `GIVEN the threat model from the security review`,
      `WHEN the mitigation lands`,
      `THEN the exploit in the repro script no longer succeeds`,
    ],
  };
  return rows[t.kind] || rows.feature;
}

function taskNotes(t) {
  const notes = {
    'graph_os': 'Touches `graph_os/indexer/` — remember to bump the schema version if node shape changes. Benchmarks live in `bench/graph/`.',
    'board_os': 'This lives in the control plane. Migrations go in `board_os/migrations/` and must be idempotent. WIP cap changes need a scrumban-config bump.',
    'thinking_os': 'Any change to the reasoning contract needs a matching entry in `docs/contracts/thinking.md` and a shadow run against last week\'s traces.',
    'adapters': 'Keep adapter contracts thin. If you\'re adding a method, ask whether it belongs in core first.',
    'templates': 'Template changes trigger drift detection (R-L-24) — heads up in #templates before merging.',
    'cli': 'CLI changes need a man-page update and a fresh `cos --help` snapshot in `docs/cli/`.',
    'docs': 'Cross-link aggressively. Every doc should answer: what is this, why does it exist, where does it live.',
    'core': 'Core changes ripple. Coordinate via #core-sync and prefer additive changes until the migration lands.',
  };
  return notes[t.swimlane] || 'No stack-specific notes yet. Add them here as the work progresses.';
}

// ====== FRONTMATTER VALIDATOR ======
// Mirrors what `validate-task-frontmatter.sh` would enforce
function validateFrontmatter(fm) {
  const errors = [];
  const warnings = [];

  const REQUIRED = ['id', 'title', 'swimlane', 'kind', 'status', 'priority', 'appetite'];
  for (const k of REQUIRED) {
    if (!fm[k] || String(fm[k]).trim() === '') errors.push(`missing required key: ${k}`);
  }

  if (fm.id && !/^TASK-\d{3}$/.test(fm.id)) errors.push(`id must match TASK-NNN (got "${fm.id}")`);
  if (fm.title && fm.title.length > 80) warnings.push(`title is ${fm.title.length} chars (soft cap 80)`);

  const KINDS = ['bug', 'feature', 'chore', 'spike', 'docs', 'refactor', 'test', 'security'];
  if (fm.kind && !KINDS.includes(fm.kind)) errors.push(`kind must be one of: ${KINDS.join(', ')}`);

  const SWIMS = (window.SWIMLANES || []).map(s => s.id);
  if (fm.swimlane && SWIMS.length && !SWIMS.includes(fm.swimlane)) errors.push(`swimlane must be one of: ${SWIMS.join(', ')}`);

  const STATUSES = ['icebox', 'ready', 'emergency', 'in_progress', 'testing', 'blocked', 'complete', 'archive'];
  if (fm.status && !STATUSES.includes(fm.status)) errors.push(`status must be one of: ${STATUSES.join(', ')}`);

  if (fm.priority && !/^P[0-3]$/.test(fm.priority)) errors.push(`priority must be P0–P3 (got "${fm.priority}")`);

  // Shape Up appetite pattern
  if (fm.appetite && !/^\d+(h|d|w)$/.test(fm.appetite)) errors.push(`appetite must match \\d+[hdw] (got "${fm.appetite}")`);

  return { errors, warnings, ok: errors.length === 0 };
}

// Serialize task + body back to a markdown file string (what we'd write to disk).
function serializeTaskMd(fm, body) {
  const ORDER = ['id', 'title', 'swimlane', 'kind', 'status', 'priority', 'appetite', 'epic', 'labels', 'agent', 'depends'];
  const out = ['---'];
  for (const k of ORDER) {
    const v = fm[k];
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      out.push(`${k}: [${v.map(x => JSON.stringify(x)).join(', ')}]`);
    } else {
      const sv = String(v);
      out.push(`${k}: ${/[:#]|^\s|\s$/.test(sv) ? JSON.stringify(sv) : sv}`);
    }
  }
  out.push('---', '', body.trimStart());
  return out.join('\n');
}

// ====== DRAWER ======
const { useState: useStateTD, useRef: useRefTD } = React;

function TaskDetailDrawer({ task, onClose, onJump, onSave, allTasks }) {
  const [mode, setMode] = useStateTD('view'); // 'view' | 'edit'
  const [editFm, setEditFm] = useStateTD(null);
  const [editBody, setEditBody] = useStateTD('');
  const [toast, setToast] = useStateTD(null);
  const [showPreview, setShowPreview] = useStateTD(true);
  const fileInputRef = useRefTD(null);
  const textareaRef = useRefTD(null);

  // Reset state when task changes
  useEffectTD(() => {
    setMode('view');
    setEditFm(null);
    setEditBody('');
    setToast(null);
  }, [task?.id]);

  useEffectTD(() => {
    if (!task) return;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (mode === 'edit') {
          if (confirm('Discard unsaved changes?')) { setMode('view'); setEditFm(null); }
        } else {
          onClose();
        }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'e' && mode === 'view') {
        e.preventDefault();
        enterEdit();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 's' && mode === 'edit') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [task, mode, editFm, editBody]);

  const md = useMemoTD(() => task ? synthesizeTaskMd(task) : '', [task]);

  const { frontmatter, body } = useMemoTD(() => {
    if (!md) return { frontmatter: {}, body: '' };
    const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(md);
    if (!m) return { frontmatter: {}, body: md };
    const fm = {};
    for (const line of m[1].split('\n')) {
      const kv = /^(\w+):\s*(.+)$/.exec(line);
      if (kv) {
        let v = kv[2];
        // parse simple arrays
        if (v.startsWith('[') && v.endsWith(']')) {
          try { fm[kv[1]] = JSON.parse(v); continue; } catch {}
        }
        // strip quotes
        if ((v.startsWith('"') && v.endsWith('"'))) v = v.slice(1, -1);
        fm[kv[1]] = v;
      }
    }
    return { frontmatter: fm, body: m[2] };
  }, [md]);

  const enterEdit = () => {
    setEditFm({ ...frontmatter, labels: Array.isArray(frontmatter.labels) ? frontmatter.labels : [], depends: Array.isArray(frontmatter.depends) ? frontmatter.depends : [] });
    setEditBody(body);
    setMode('edit');
  };

  const validation = useMemoTD(() => {
    if (mode !== 'edit' || !editFm) return { ok: true, errors: [], warnings: [] };
    return validateFrontmatter(editFm);
  }, [mode, editFm]);

  const handleSave = () => {
    const v = validateFrontmatter(editFm);
    if (!v.ok) {
      setToast({ kind: 'error', lines: ['validate-task-frontmatter.sh → FAIL', ...v.errors.map(e => `  × ${e}`)] });
      return;
    }
    const fileContents = serializeTaskMd(editFm, editBody);
    // Would write to disk here; we just toast a realistic hook chain
    setToast({ kind: 'ok', lines: [
      'validate-task-frontmatter.sh → ok',
      `writing ${filePath} (${fileContents.length} bytes)`,
      'sync-scrumban-config.sh → v13 → ok',
      'capture-work-log.sh → appended',
    ] });
    if (onSave) onSave(task.id, editFm, editBody);
    setTimeout(() => { setMode('view'); setEditFm(null); setToast(null); }, 1600);
  };

  const attachImage = (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      const url = reader.result;
      const alt = file.name.replace(/\.[^.]+$/, '');
      const tag = `\n\n![${alt}](${url})\n\n`;
      const ta = textareaRef.current;
      if (ta) {
        const pos = ta.selectionStart;
        const before = editBody.slice(0, pos);
        const after = editBody.slice(pos);
        setEditBody(before + tag + after);
        setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = pos + tag.length; }, 0);
      } else {
        setEditBody(editBody + tag);
      }
    };
    reader.readAsDataURL(file);
  };

  const handlePaste = (e) => {
    const items = e.clipboardData?.items || [];
    for (const it of items) {
      if (it.kind === 'file' && it.type.startsWith('image/')) {
        e.preventDefault();
        attachImage(it.getAsFile());
        return;
      }
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) attachImage(f);
  };

  if (!task) return null;

  const kind = window.KIND_COLORS[task.kind];
  const lane = window.SWIMLANES.find(s => s.id === task.swimlane);
  const priColor = { P0: '#dc2626', P1: '#ea580c', P2: '#ca8a04', P3: '#64748b' }[task.priority];
  const viewTitle = mode === 'edit' ? (editFm?.title || task.title) : task.title;
  const filePath = `docs/tasks/${task.id}-${viewTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)}.md`;

  const handleBodyClick = (e) => {
    if (mode === 'edit') return;
    const a = e.target.closest('.md-tasklink');
    if (a) {
      e.preventDefault();
      const id = a.dataset.task;
      const t = allTasks.find(x => x.id === id);
      if (t) onJump(t);
    }
  };

  return (
    <>
      <div
        onClick={() => { if (mode === 'view') onClose(); }}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(10,12,16,.55)',
          zIndex: 80, backdropFilter: 'blur(3px)',
          animation: 'td-fade-in 180ms ease',
        }}
      />

      <div
        onClick={handleBodyClick}
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 'min(960px, 94vw)',
          background: 'var(--col-bg)',
          borderLeft: '1px solid var(--col-border)',
          boxShadow: '-30px 0 60px rgba(0,0,0,.3)',
          zIndex: 81,
          display: 'flex', flexDirection: 'column',
          animation: 'td-slide-in 220ms cubic-bezier(.22,.61,.36,1)',
        }}
      >
        <DrawerHeader
          task={task} filePath={filePath} mode={mode}
          lane={lane} kind={kind} priColor={priColor}
          editFm={editFm} setEditFm={setEditFm}
          onClose={onClose}
          onEnterEdit={enterEdit}
          onSave={handleSave}
          onCancel={() => {
            if (confirm('Discard unsaved changes?')) { setMode('view'); setEditFm(null); }
          }}
          onAttachImage={() => fileInputRef.current?.click()}
          validation={validation}
          showPreview={showPreview}
          setShowPreview={setShowPreview}
        />

        {mode === 'view' ? (
          <div style={{
            flex: 1, overflow: 'auto',
            padding: '18px 28px 40px',
            background: 'var(--col-bg)',
          }}>
            <div className="md-body">{renderMd(body)}</div>
          </div>
        ) : (
          <EditBody
            body={editBody} setBody={setEditBody}
            textareaRef={textareaRef}
            onPaste={handlePaste}
            onDrop={handleDrop}
            showPreview={showPreview}
          />
        )}

        <DrawerFooter task={task} mode={mode} toast={toast} />

        <input
          ref={fileInputRef} type="file" accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => { attachImage(e.target.files?.[0]); e.target.value = ''; }}
        />
      </div>
    </>
  );
}

// ====== HEADER ======
function DrawerHeader({ task, filePath, mode, lane, kind, priColor, editFm, setEditFm, onClose, onEnterEdit, onSave, onCancel, onAttachImage, validation, showPreview, setShowPreview }) {
  const fm = mode === 'edit' ? editFm : {
    status: task.status, swimlane: task.swimlane, kind: task.kind,
    priority: task.priority, appetite: task.appetite, epic: task.epic,
    agent: task.agent, labels: task.labels, title: task.title,
  };

  return (
    <div style={{
      padding: '14px 20px 12px',
      borderBottom: '1px solid var(--col-border)',
      background: 'linear-gradient(180deg, var(--col-bg) 0, var(--board-grain) 100%)',
      flex: '0 0 auto',
    }}>
      {/* top row: filepath + actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11, color: 'var(--ink-faint)',
          letterSpacing: '.04em',
          display: 'flex', alignItems: 'center', gap: 6,
          flex: 1, minWidth: 0,
        }}>
          <span style={{ color: mode === 'edit' ? 'var(--accent)' : 'var(--ink-soft)' }}>
            {mode === 'edit' ? '✎' : '📄'}
          </span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {filePath}
          </span>
          {mode === 'edit' && <span style={{
            padding: '1px 6px', fontSize: 9, fontWeight: 700, letterSpacing: '.08em',
            background: 'var(--accent)', color: 'white', borderRadius: 2,
          }}>EDITING</span>}
        </div>

        {mode === 'view' ? (
          <>
            <HeaderBtn onClick={onEnterEdit} title="Edit (⌘E)">✎ edit</HeaderBtn>
            <HeaderBtn onClick={onClose} title="Close (esc)">esc</HeaderBtn>
          </>
        ) : (
          <>
            <HeaderBtn onClick={() => setShowPreview(!showPreview)} title="Toggle preview">
              {showPreview ? '◨ split' : '□ full'}
            </HeaderBtn>
            <HeaderBtn onClick={onAttachImage} title="Attach image">🖼 image</HeaderBtn>
            <HeaderBtn onClick={onCancel} title="Discard">cancel</HeaderBtn>
            <HeaderBtn
              onClick={onSave}
              disabled={!validation.ok}
              primary
              title="Save (⌘S)"
            >
              ✓ save
            </HeaderBtn>
          </>
        )}
      </div>

      {/* title */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 14, fontWeight: 700,
          color: 'var(--accent)',
          padding: '2px 7px',
          background: 'var(--board-grain)',
          border: '1px solid var(--col-border)',
          borderRadius: 3,
        }}>{task.id}</span>
        {mode === 'edit' ? (
          <input
            value={fm.title || ''}
            onChange={(e) => setEditFm({ ...editFm, title: e.target.value })}
            style={{
              flex: 1, margin: 0, padding: '4px 8px',
              fontFamily: "'Inter', system-ui, sans-serif",
              fontSize: 22, fontWeight: 600, lineHeight: 1.25,
              color: 'var(--ink)', background: 'var(--board-grain)',
              border: '1px solid var(--col-border)', borderRadius: 3,
              letterSpacing: '-.01em', outline: 'none',
            }}
          />
        ) : (
          <h1 style={{
            margin: 0, flex: 1,
            fontFamily: "'Inter', system-ui, sans-serif",
            fontSize: 22, fontWeight: 600, lineHeight: 1.25,
            color: 'var(--ink)', letterSpacing: '-.01em',
          }}>{task.title}</h1>
        )}
      </div>

      {/* metadata — editable dropdowns in edit mode */}
      {mode === 'edit' ? (
        <EditableFmRow fm={editFm} setFm={setEditFm} validation={validation} />
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
          <Pill label="status" value={task.status.toUpperCase()} />
          <Pill label="swimlane" value={task.swimlane} dot={lane?.color} />
          <Pill label="kind" value={task.kind} dot={kind.chip} />
          <Pill label="priority" value={task.priority} valueColor={priColor} strong />
          <Pill label="appetite" value={task.appetite} />
          {task.epic && <Pill label="epic" value={task.epic} />}
          {task.agent && <Pill label="agent" value={task.agent} />}
          {task.labels.map(l => (
            <span key={l} style={{
              fontSize: 10, padding: '2px 7px', background: 'transparent',
              color: 'var(--ink-soft)', border: '1px dashed var(--col-border)',
              borderRadius: 10,
            }}>#{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function HeaderBtn({ children, primary, disabled, ...rest }) {
  return (
    <button
      disabled={disabled}
      {...rest}
      style={{
        background: primary ? 'var(--accent)' : 'transparent',
        color: primary ? 'white' : 'var(--ink-soft)',
        border: '1px solid ' + (primary ? 'var(--accent)' : 'var(--col-border)'),
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11, fontWeight: primary ? 700 : 500,
        padding: '3px 10px', borderRadius: 3,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : 1,
        letterSpacing: '.02em',
      }}
    >{children}</button>
  );
}

// ====== EDITABLE METADATA ROW ======
function EditableFmRow({ fm, setFm, validation }) {
  const kinds = Object.keys(window.KIND_COLORS || {});
  const swims = (window.SWIMLANES || []).map(s => s.id);
  const statuses = ['icebox', 'ready', 'emergency', 'in_progress', 'testing', 'blocked', 'complete', 'archive'];
  const priorities = ['P0', 'P1', 'P2', 'P3'];
  const epics = ['', ...(window.EPICS || []).map(e => e.id)];
  const set = (k, v) => setFm({ ...fm, [k]: v });

  return (
    <div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: 6,
        fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
      }}>
        <FmField label="status">
          <Select value={fm.status} onChange={v => set('status', v)} options={statuses} />
        </FmField>
        <FmField label="swimlane">
          <Select value={fm.swimlane} onChange={v => set('swimlane', v)} options={swims} />
        </FmField>
        <FmField label="kind">
          <Select value={fm.kind} onChange={v => set('kind', v)} options={kinds} />
        </FmField>
        <FmField label="priority">
          <Select value={fm.priority} onChange={v => set('priority', v)} options={priorities} />
        </FmField>
        <FmField label="appetite" invalid={fm.appetite && !/^\d+(h|d|w)$/.test(fm.appetite)}>
          <input
            value={fm.appetite || ''}
            onChange={e => set('appetite', e.target.value)}
            placeholder="4h"
            style={fmInputStyle}
          />
        </FmField>
        <FmField label="epic">
          <Select value={fm.epic || ''} onChange={v => set('epic', v || null)} options={epics} />
        </FmField>
        <FmField label="labels" span>
          <input
            value={(fm.labels || []).join(', ')}
            onChange={e => set('labels', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
            placeholder="comma, separated"
            style={fmInputStyle}
          />
        </FmField>
      </div>
      {(validation.errors.length > 0 || validation.warnings.length > 0) && (
        <div style={{
          marginTop: 8, padding: '6px 10px',
          background: validation.errors.length ? 'rgba(220,38,38,.08)' : 'rgba(234,88,12,.08)',
          border: '1px solid ' + (validation.errors.length ? 'rgba(220,38,38,.3)' : 'rgba(234,88,12,.3)'),
          borderRadius: 3,
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, lineHeight: 1.6,
        }}>
          <div style={{ color: validation.errors.length ? '#dc2626' : '#ea580c', fontWeight: 700, marginBottom: 2 }}>
            validate-task-frontmatter.sh → {validation.errors.length ? 'FAIL' : 'warn'}
          </div>
          {validation.errors.map((e, i) => <div key={i} style={{ color: '#dc2626' }}>× {e}</div>)}
          {validation.warnings.map((w, i) => <div key={i} style={{ color: '#ea580c' }}>! {w}</div>)}
        </div>
      )}
    </div>
  );
}

const fmInputStyle = {
  width: '100%', padding: '3px 6px',
  background: 'var(--col-bg)',
  border: '1px solid var(--col-border)', borderRadius: 2,
  fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
  color: 'var(--ink)', outline: 'none',
};

function FmField({ label, children, invalid, span }) {
  return (
    <div style={{
      gridColumn: span ? '1 / -1' : 'auto',
      display: 'flex', flexDirection: 'column', gap: 2,
    }}>
      <label style={{
        fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
        color: invalid ? '#dc2626' : 'var(--ink-faint)', fontWeight: 600,
      }}>{label}</label>
      {children}
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      style={fmInputStyle}
    >
      {options.map(o => <option key={o} value={o}>{o || '(none)'}</option>)}
    </select>
  );
}

// ====== EDIT BODY (textarea + preview) ======
function EditBody({ body, setBody, textareaRef, onPaste, onDrop, showPreview }) {
  return (
    <div
      onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
      onDrop={onDrop}
      style={{
        flex: 1, overflow: 'hidden', display: 'grid',
        gridTemplateColumns: showPreview ? '1fr 1fr' : '1fr',
        background: 'var(--col-bg)',
      }}
    >
      <textarea
        ref={textareaRef}
        value={body}
        onChange={e => setBody(e.target.value)}
        onPaste={onPaste}
        spellCheck={false}
        style={{
          border: 'none', outline: 'none', resize: 'none',
          padding: '18px 22px',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 13, lineHeight: 1.65,
          color: 'var(--ink)', background: 'var(--col-bg)',
          borderRight: showPreview ? '1px solid var(--col-border)' : 'none',
        }}
      />
      {showPreview && (
        <div style={{
          overflow: 'auto', padding: '18px 22px',
          background: 'var(--board-grain)',
        }}>
          <div className="md-body">{renderMd(body)}</div>
        </div>
      )}
    </div>
  );
}

// ====== FOOTER ======
function DrawerFooter({ task, mode, toast }) {
  if (toast) {
    return (
      <div style={{
        flex: '0 0 auto',
        padding: '8px 16px',
        borderTop: '1px solid var(--col-border)',
        background: toast.kind === 'ok' ? 'rgba(22,163,74,.1)' : 'rgba(220,38,38,.1)',
        fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5,
        color: toast.kind === 'ok' ? '#15803d' : '#dc2626',
        lineHeight: 1.55,
        maxHeight: 110, overflow: 'auto',
      }}>
        {toast.lines.map((l, i) => (
          <div key={i} style={{ fontWeight: i === 0 ? 700 : 400 }}>{l}</div>
        ))}
      </div>
    );
  }
  return (
    <div style={{
      flex: '0 0 auto',
      padding: '8px 16px',
      borderTop: '1px solid var(--col-border)',
      background: 'var(--board-grain)',
      display: 'flex', gap: 6, alignItems: 'center',
      fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5,
      color: 'var(--ink-faint)',
    }}>
      <span style={{ color: 'var(--ink-soft)' }}>$</span>
      {mode === 'edit' ? (
        <>
          <span>paste or drop images · ⌘S save · esc discard</span>
          <span style={{ flex: 1 }} />
          <span style={{ opacity: .7 }}>cos task update {task.id}</span>
        </>
      ) : (
        <>
          <span>cos edit {task.id}</span>
          <span style={{ opacity: .4, marginLeft: 8 }}>·</span>
          <span>cos log {task.id} "msg"</span>
          <span style={{ opacity: .4, marginLeft: 8 }}>·</span>
          <span>cos move {task.id} complete</span>
          <span style={{ flex: 1 }} />
          <span style={{ opacity: .7 }}>⌘E edit · esc close</span>
        </>
      )}
    </div>
  );
}

function Pill({ label, value, dot, strong, valueColor }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 7px 2px 5px',
      background: 'var(--board-grain)',
      border: '1px solid var(--col-border)',
      borderRadius: 3,
    }}>
      {dot && <span style={{
        width: 7, height: 7, borderRadius: 2, background: dot,
      }} />}
      <span style={{ color: 'var(--ink-faint)' }}>{label}</span>
      <span style={{
        color: valueColor || 'var(--ink)',
        fontWeight: strong ? 700 : 500,
      }}>{value}</span>
    </span>
  );
}

Object.assign(window, { TaskDetailDrawer });
