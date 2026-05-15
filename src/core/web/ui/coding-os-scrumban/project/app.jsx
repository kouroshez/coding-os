// cos board — main app
const { useState: useStateA, useEffect: useEffectA, useMemo: useMemoA, useRef: useRefA } = React;

const FALLBACK_TWEAKS = {
  theme: 'light', density: 'cozy', agentSurface: true,
  showWipViolation: true, filterKind: 'all', filterEpic: 'all', aesthetic: 'whiteboard',
};

function useEditMode(initial) {
  const [tweaks, setTweaks] = useStateA(initial || FALLBACK_TWEAKS);
  const [visible, setVisible] = useStateA(false);

  useEffectA(() => {
    const handler = (e) => {
      if (!e.data || typeof e.data !== 'object') return;
      if (e.data.type === '__activate_edit_mode') setVisible(true);
      if (e.data.type === '__deactivate_edit_mode') setVisible(false);
    };
    window.addEventListener('message', handler);
    window.parent?.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  useEffectA(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-aesthetic', tweaks.aesthetic);
  }, [tweaks.theme, tweaks.aesthetic]);

  return [tweaks, setTweaks, visible, setVisible];
}

// ---------- ZOOM CONTROLS ----------
function ZoomControls({ zoom, setZoom, collapsed, onExpandAll, onCollapseEmpty }) {
  const pct = Math.round(zoom * 100);
  return (
    <div style={{
      position: 'fixed', right: 20, bottom: 20, zIndex: 45,
      display: 'flex', alignItems: 'stretch', gap: 6,
      fontFamily: 'JetBrains Mono, monospace', fontSize: 11,
      pointerEvents: 'auto',
    }}>
      {/* lane collapse cluster */}
      <div style={{
        display: 'flex', alignItems: 'center',
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 4,
        boxShadow: '0 4px 14px rgba(0,0,0,.12)',
        overflow: 'hidden',
      }}>
        <ZoomBtn onClick={onCollapseEmpty} title="Collapse empty lanes">⊟ empty</ZoomBtn>
        <ZoomDiv />
        <ZoomBtn onClick={onExpandAll} disabled={collapsed.size === 0} title={`Expand all (${collapsed.size} collapsed)`}>
          ⊞ expand
        </ZoomBtn>
      </div>

      {/* zoom cluster */}
      <div style={{
        display: 'flex', alignItems: 'center',
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 4,
        boxShadow: '0 4px 14px rgba(0,0,0,.12)',
        overflow: 'hidden',
      }}>
        <ZoomBtn onClick={() => setZoom(zoom - 0.1)} disabled={zoom <= 0.5} title="Zoom out (⌘-)">−</ZoomBtn>
        <ZoomDiv />
        <button
          onClick={() => setZoom(1)}
          title="Reset (⌘0)"
          style={{
            padding: '0 10px', minWidth: 54, height: 30,
            background: 'transparent', border: 'none',
            color: pct === 100 ? 'var(--ink-faint)' : 'var(--accent)',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11, fontWeight: 700, cursor: 'pointer',
          }}>{pct}%</button>
        <ZoomDiv />
        <ZoomBtn onClick={() => setZoom(zoom + 0.1)} disabled={zoom >= 1.5} title="Zoom in (⌘+)">+</ZoomBtn>
        <ZoomDiv />
        <input
          type="range" min={0.5} max={1.5} step={0.05}
          value={zoom}
          onChange={e => setZoom(parseFloat(e.target.value))}
          style={{
            width: 90, margin: '0 10px', accentColor: 'var(--accent)',
          }}
        />
      </div>
    </div>
  );
}

function ZoomBtn({ children, onClick, disabled, title }) {
  return (
    <button
      onClick={onClick} disabled={disabled} title={title}
      style={{
        height: 30, minWidth: 30, padding: '0 9px',
        background: 'transparent', border: 'none',
        color: disabled ? 'var(--ink-faint)' : 'var(--ink)',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 13, fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.35 : 1,
      }}
    >{children}</button>
  );
}
function ZoomDiv() { return <div style={{ width: 1, background: 'var(--col-border)', alignSelf: 'stretch' }} />; }

// ---------- TOP BAR ----------
function TopBar({ tweaks, onOpenTweaks, stats, onToggleStream, streamOpen, onToggleLegend, legendOpen, onCreate }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '10px 18px',
      borderBottom: '2px solid var(--line)',
      background: 'var(--board)',
      position: 'relative', zIndex: 10,
    }}>
      <div style={{
        fontFamily: "'Permanent Marker', cursive",
        fontSize: 26, letterSpacing: '.02em',
        color: 'var(--accent)',
        lineHeight: 1,
      }}>cos board</div>
      <div style={{
        fontFamily: "'Caveat', cursive",
        fontSize: 18, color: 'var(--ink-soft)',
        marginLeft: -4, marginTop: 6,
      }}>— scrumban · coding-os</div>

      <div style={{
        marginLeft: 20,
        display: 'flex', alignItems: 'stretch', gap: 0,
        fontFamily: 'JetBrains Mono, monospace', fontSize: 10.5,
        border: '1px solid var(--col-border)', borderRadius: 4,
        background: 'var(--col-bg)',
        overflow: 'hidden',
      }}>
        <StatCell label="THROUGHPUT" value={stats.throughput} unit="/wk" hint={`last 7d: ${stats.throughputLast7}`} />
        <StatCell label="LEAD TIME" value={stats.leadTime} unit="d p50" hint={`p90 ${stats.leadTimeP90}d`} />
        <StatCell label="CYCLE" value={stats.cycleTime} unit="d p50" />
        <StatCell label="WIP" value={stats.wipTotal} unit={`/${stats.wipCap}`} tone={stats.wipOver ? 'red' : null} hint={stats.wipOver ? `${stats.wipOver} col over cap` : 'within caps'} />
        <StatCell label="BLOCKED" value={stats.blocked} unit="" tone={stats.blocked > 0 ? 'amber' : null} />
        <StatCell label="STALE" value={stats.stale} unit="" hint=">3d idle" tone={stats.stale > 2 ? 'amber' : null} />
        <StatCell label="P0" value={stats.p0} unit="open" tone={stats.p0 > 0 ? 'red' : null} />
        <StatCell label="EMERG" value={stats.emergency} unit="" tone={stats.emergency > 0 ? 'red' : null} last />
      </div>

      <div style={{ flex: 1 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: 'var(--ink-faint)' }}>live:</span>
          {window.AGENTS.map(a => <AgentPip key={a.id} agentId={a.id} />)}
        </div>

        <div style={{ width: 1, height: 22, background: 'var(--col-border)', margin: '0 4px' }} />

        <button onClick={onCreate} title="New task (n)" style={{
          padding: '6px 12px', fontSize: 11,
          fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
          background: 'var(--accent)', color: 'white',
          border: '1.5px solid var(--accent)',
          borderRadius: 4, cursor: 'pointer',
          letterSpacing: '.02em',
        }}>＋ new</button>

        <TopBtn onClick={onToggleLegend} active={legendOpen}>⁂ legend</TopBtn>
        <TopBtn onClick={onToggleStream} active={streamOpen}>⎌ stream</TopBtn>
        <TopBtn onClick={onOpenTweaks}>⚙ tweaks</TopBtn>
      </div>
    </div>
  );
}

function TopBtn({ children, onClick, active }) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 10px', fontSize: 11,
      fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
      background: active ? 'var(--accent)' : 'transparent',
      color: active ? 'white' : 'var(--ink)',
      border: '1.5px solid ' + (active ? 'var(--accent)' : 'var(--line-soft)'),
      borderRadius: 4, cursor: 'pointer',
    }}>{children}</button>
  );
}

function StatCell({ label, value, unit, hint, tone, last }) {
  const color = tone === 'red' ? '#dc2626' : tone === 'amber' ? '#ea580c' : 'var(--ink)';
  return (
    <div title={hint || ''} style={{
      padding: '4px 12px',
      borderRight: last ? 'none' : '1px solid var(--col-border)',
      display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
      gap: 1, minWidth: 58,
      background: tone === 'red' ? 'rgba(220,38,38,.06)' : tone === 'amber' ? 'rgba(234,88,12,.06)' : 'transparent',
    }}>
      <div style={{
        fontSize: 8, letterSpacing: '.1em', fontWeight: 700,
        color: tone ? color : 'var(--ink-faint)',
      }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color, lineHeight: 1 }}>{value}</span>
        {unit && <span style={{ fontSize: 9, color: 'var(--ink-faint)' }}>{unit}</span>}
      </div>
    </div>
  );
}

// ---------- LIVE STREAM DRAWER ----------
function LiveStream({ open, onClose }) {
  if (!open) return null;
  const kindColor = {
    work_log:   '#16a34a',
    hook:       '#d97706',
    transition: '#7c3aed',
    search:     '#0891b2',
    pick:       '#db2777',
  };
  return (
    <div style={{
      position: 'fixed', top: 56, right: 14, bottom: 14,
      width: 380, zIndex: 50,
      background: 'var(--col-bg)',
      border: '1px solid var(--col-border)',
      borderRadius: 6,
      boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
      display: 'flex', flexDirection: 'column',
      fontFamily: 'JetBrains Mono, monospace',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px', borderBottom: '1px solid var(--col-border)',
      }}>
        <div style={{
          fontFamily: "'Permanent Marker', cursive",
          fontSize: 14, letterSpacing: '.04em', color: 'var(--accent)',
        }}>AGENT STREAM</div>
        <span style={{ fontSize: 10, color: 'var(--ink-faint)' }}>
          <span style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
            background: '#16a34a', marginRight: 4, animation: 'pulse 1.5s infinite',
          }} />
          WS 127.0.0.1:9000
        </span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--ink-faint)',
          cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0,
        }}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 4px' }}>
        {window.LIVE_STREAM.map((ev, i) => (
          <div key={i} style={{
            padding: '6px 10px',
            borderBottom: '1px dotted var(--col-border)',
            fontSize: 10.5, lineHeight: 1.4,
            display: 'flex', gap: 6, alignItems: 'flex-start',
          }}>
            <span style={{ color: 'var(--ink-faint)', flexShrink: 0 }}>{ev.t}</span>
            <AgentPip agentId={ev.agent} />
            <span style={{
              color: kindColor[ev.kind],
              fontWeight: 700,
              fontSize: 9,
              flexShrink: 0,
              padding: '1px 4px',
              background: `${kindColor[ev.kind]}18`,
              borderRadius: 2,
              textTransform: 'uppercase',
              letterSpacing: '.04em',
            }}>{ev.kind}</span>
            <div style={{ flex: 1, minWidth: 0, color: 'var(--ink)' }}>
              {ev.task && <span style={{ color: 'var(--accent)', fontWeight: 600, marginRight: 4 }}>{ev.task}</span>}
              <span style={{ color: 'var(--ink-soft)' }}>{ev.msg}</span>
            </div>
          </div>
        ))}
      </div>
      <div style={{
        padding: '8px 12px',
        borderTop: '1px solid var(--col-border)',
        fontSize: 10, color: 'var(--ink-faint)',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>capture-work-log.sh · enforce-wip-limit.sh</span>
        <span>{window.LIVE_STREAM.length} events</span>
      </div>
    </div>
  );
}

// ---------- BOARD ----------
function Board() {
  const [tweaks, setTweaks, tweaksVisible, setTweaksVisible] = useEditMode(window.TWEAK_DEFAULTS);
  const [tasks, setTasks] = useStateA(window.TASKS);
  const [dragging, setDragging] = useStateA(null);
  const [dragTarget, setDragTarget] = useStateA(null);
  const [streamOpen, setStreamOpen] = useStateA(true);
  const [legendOpen, setLegendOpen] = useStateA(false);
  const [zoom, setZoom] = useStateA(() => {
    const saved = parseFloat(localStorage.getItem('cos-zoom'));
    return Number.isFinite(saved) && saved >= 0.5 && saved <= 1.5 ? saved : 1;
  });
  const [collapsed, setCollapsed] = useStateA(() => {
    try { return new Set(JSON.parse(localStorage.getItem('cos-collapsed') || '[]')); }
    catch { return new Set(); }
  });

  useEffectA(() => { localStorage.setItem('cos-zoom', String(zoom)); }, [zoom]);
  useEffectA(() => {
    localStorage.setItem('cos-collapsed', JSON.stringify([...collapsed]));
  }, [collapsed]);

  const toggleLane = (laneId) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(laneId)) next.delete(laneId); else next.add(laneId);
      return next;
    });
  };

  const setZoomClamped = (v) => setZoom(Math.min(1.5, Math.max(0.5, Math.round(v * 100) / 100)));

  // keyboard: cmd +/-/0
  useEffectA(() => {
    const onKey = (e) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === '=' || e.key === '+') { e.preventDefault(); setZoomClamped(zoom + 0.1); }
      else if (e.key === '-') { e.preventDefault(); setZoomClamped(zoom - 0.1); }
      else if (e.key === '0') { e.preventDefault(); setZoomClamped(1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);
  const [flashWip, setFlashWip] = useStateA(null);
  const [createOpen, setCreateOpen] = useStateA(false);
  const [justCreated, setJustCreated] = useStateA(null);
  const [highlight, setHighlight] = useStateA(null);
  const [detailTask, setDetailTask] = useStateA(null);

  useEffectA(() => {
    const onKey = (e) => {
      if (e.key === 'n' && !e.metaKey && !e.ctrlKey && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        setCreateOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const nextId = useMemoA(() => {
    const maxN = tasks.reduce((m, t) => Math.max(m, parseInt(t.id.replace('TASK-', ''), 10) || 0), 0);
    return maxN + 1;
  }, [tasks]);

  const handleCreate = (task) => {
    setTasks(prev => [...prev, task]);
    setJustCreated(task.id);
    setTimeout(() => setJustCreated(null), 2800);
  };

  const filteredTasks = useMemoA(() => {
    return tasks.filter(t => {
      if (tweaks.filterKind !== 'all' && t.kind !== tweaks.filterKind) return false;
      if (tweaks.filterEpic !== 'all' && t.epic !== tweaks.filterEpic) return false;
      if (tweaks.filterSwim && tweaks.filterSwim !== 'all' && t.swimlane !== tweaks.filterSwim) return false;
      return true;
    });
  }, [tasks, tweaks.filterKind, tweaks.filterEpic, tweaks.filterSwim]);

  const taskCounts = useMemoA(() => {
    const c = { kind: {}, swim: {}, priority: {} };
    for (const t of tasks) {
      c.kind[t.kind] = (c.kind[t.kind] || 0) + 1;
      c.swim[t.swimlane] = (c.swim[t.swimlane] || 0) + 1;
      c.priority[t.priority] = (c.priority[t.priority] || 0) + 1;
    }
    return c;
  }, [tasks]);

  // group by (swimlane, column)
  const cellMap = useMemoA(() => {
    const m = {};
    for (const l of window.SWIMLANES) {
      m[l.id] = {};
      for (const c of window.COLUMNS) m[l.id][c.id] = [];
    }
    for (const t of filteredTasks) {
      if (m[t.swimlane] && m[t.swimlane][t.status]) m[t.swimlane][t.status].push(t);
    }
    return m;
  }, [filteredTasks]);

  const wipStats = useMemoA(() => {
    return window.COLUMNS
      .filter(c => c.wip != null)
      .map(c => {
        const count = filteredTasks.filter(t => t.status === c.id).length;
        return { id: c.id, count, wip: c.wip, violated: count > c.wip };
      });
  }, [filteredTasks]);

  const stats = useMemoA(() => {
    const done = tasks.filter(t => t.status === 'complete' || t.status === 'archive');
    const wipTotal = tasks.filter(t => ['in_progress', 'testing', 'emergency'].includes(t.status)).length;
    const wipCap = window.COLUMNS.filter(c => c.wip != null).reduce((a, c) => a + c.wip, 0);
    const wipOver = wipStats.filter(s => s.violated).length;
    return {
      throughput: 14, // tasks/week (last 4w avg)
      throughputLast7: 11,
      leadTime: 4.2,
      leadTimeP90: 9.1,
      cycleTime: 2.1,
      wipTotal, wipCap, wipOver,
      blocked: tasks.filter(t => t.status === 'blocked').length,
      stale: tasks.filter(t => t.stale).length,
      p0: tasks.filter(t => t.priority === 'P0' && !['complete', 'archive'].includes(t.status)).length,
      emergency: tasks.filter(t => t.status === 'emergency').length,
    };
  }, [tasks, wipStats]);

  const onDragStart = (e, task) => {
    setDragging(task);
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', task.id); } catch {}
  };

  const onDragEnd = () => {
    setDragging(null);
    setDragTarget(null);
  };

  const onDragOver = (e, laneId, colId) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragTarget(`${laneId}:${colId}`);
  };

  const onDrop = (e, laneId, colId) => {
    e.preventDefault();
    if (!dragging) return;
    // wip pre-check
    const col = window.COLUMNS.find(c => c.id === colId);
    const currentInCol = tasks.filter(t => t.status === colId && t.id !== dragging.id).length;
    if (col.wip != null && currentInCol >= col.wip && tweaks.showWipViolation && (colId === 'in_progress' || colId === 'emergency')) {
      setFlashWip(colId);
      setTimeout(() => setFlashWip(null), 1200);
      // soft-allow but indicate warning
    }
    setTasks(prev => prev.map(t => t.id === dragging.id ? { ...t, status: colId, swimlane: laneId } : t));
    setDragging(null);
    setDragTarget(null);
  };

  const totalWidth = window.COLUMNS.length * 240 + 130;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar
        tweaks={tweaks}
        stats={stats}
        onOpenTweaks={() => setTweaksVisible(v => !v)}
        streamOpen={streamOpen}
        onToggleStream={() => setStreamOpen(v => !v)}
        legendOpen={legendOpen}
        onToggleLegend={() => setLegendOpen(v => !v)}
        onCreate={() => setCreateOpen(true)}
      />

      <div style={{
        flex: 1, overflow: 'auto',
        position: 'relative',
      }}>
        <div style={{
          transform: `scale(${zoom})`,
          transformOrigin: 'top left',
          width: `${100 / zoom}%`,
          minWidth: totalWidth,
        }}>
          {/* column headers row */}
          <div style={{
            display: 'flex',
            position: 'sticky', top: 0, zIndex: 5,
            background: 'var(--board)',
            borderBottom: '2px solid var(--line)',
          }}>
            <div style={{
              width: 130, minWidth: 130, flexShrink: 0,
              borderRight: '2px solid var(--line)',
              position: 'sticky', left: 0, zIndex: 2,
              background: 'var(--board)',
            }} />
            {window.COLUMNS.map(col => {
              const count = filteredTasks.filter(t => t.status === col.id).length;
              return (
                <div key={col.id} style={{
                  flex: '1 1 0', minWidth: 190,
                  borderRight: '1px dashed var(--col-border)',
                }}>
                  <ColumnHeader
                    col={col} count={count}
                    showWipViolation={tweaks.showWipViolation}
                  />
                </div>
              );
            })}
          </div>

          {/* swimlane rows */}
          {window.SWIMLANES.map((lane, laneIdx) => {
            const laneCount = filteredTasks.filter(t => t.swimlane === lane.id).length;
            const isCollapsed = collapsed.has(lane.id);
            if (isCollapsed) {
              return (
                <div key={lane.id}
                  onClick={() => toggleLane(lane.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '7px 14px 7px 20px',
                    borderBottom: '1px solid var(--col-border)',
                    borderLeft: `6px solid ${lane.accent}`,
                    background: laneIdx % 2 ? 'rgba(0,0,0,.02)' : 'var(--board-grain)',
                    cursor: 'pointer',
                    fontFamily: "'Permanent Marker', cursive",
                    fontSize: 14, color: 'var(--ink-soft)',
                    position: 'sticky', left: 0,
                  }}>
                  <span style={{ color: 'var(--ink-faint)', fontSize: 12 }}>▸</span>
                  <span>{lane.label}</span>
                  <span style={{
                    fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
                    color: 'var(--ink-faint)', fontWeight: 500,
                  }}>· {laneCount} task{laneCount !== 1 ? 's' : ''}</span>
                  <span style={{ flex: 1 }} />
                  <span style={{
                    fontFamily: 'JetBrains Mono, monospace', fontSize: 9,
                    color: 'var(--ink-faint)',
                  }}>click to expand</span>
                </div>
              );
            }
            return (
              <div key={lane.id} style={{
                display: 'flex',
                borderBottom: '1px solid var(--col-border)',
                background: laneIdx % 2 ? 'rgba(0,0,0,.015)' : 'transparent',
                minHeight: 140,
              }}>
                <SwimlaneLabel
                  lane={lane} taskCount={laneCount}
                  onCollapse={() => toggleLane(lane.id)}
                />
                {window.COLUMNS.map(col => (
                  <Cell
                    key={col.id}
                    col={col} lane={lane}
                    tasks={cellMap[lane.id][col.id]}
                    density={tweaks.density}
                    agentSurface={tweaks.agentSurface}
                    highlight={highlight}
                    quietMode={tweaks.quietMode}
                    draggingId={dragging?.id}
                    isDragTarget={dragTarget === `${lane.id}:${col.id}`}
                    onDragOver={(e) => onDragOver(e, lane.id, col.id)}
                    onDrop={(e) => onDrop(e, lane.id, col.id)}
                    onDragStart={onDragStart}
                    onDragEnd={onDragEnd}
                    onCardClick={setDetailTask}
                  />
                ))}
              </div>
            );
          })}

          {/* footer marker line */}
          <div style={{
            padding: '14px 18px 24px',
            fontFamily: "'Caveat', cursive",
            fontSize: 14, color: 'var(--ink-faint)',
            textAlign: 'center',
          }}>
            drag cards between columns · WIP caps enforced by workflow.transition() · SSoT is the Markdown frontmatter
          </div>
        </div>

        <ZoomControls
          zoom={zoom} setZoom={setZoomClamped}
          collapsed={collapsed}
          onExpandAll={() => setCollapsed(new Set())}
          onCollapseEmpty={() => {
            const empty = new Set();
            for (const l of window.SWIMLANES) {
              if (!tasks.some(t => t.swimlane === l.id)) empty.add(l.id);
            }
            setCollapsed(empty);
          }}
        />
      </div>

      <LiveStream open={streamOpen && tweaks.agentSurface} onClose={() => setStreamOpen(false)} />

      <TweaksPanel
        tweaks={tweaks} setTweaks={setTweaks}
        visible={tweaksVisible}
        onClose={() => setTweaksVisible(false)}
      />

      <CreateTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={handleCreate}
        nextId={nextId}
      />

      <TaskDetailDrawer
        task={detailTask}
        allTasks={tasks}
        onClose={() => setDetailTask(null)}
        onJump={(t) => setDetailTask(t)}
        onSave={(taskId, fm, body) => {
          setTasks(prev => prev.map(t => t.id === taskId ? {
            ...t,
            title: fm.title ?? t.title,
            swimlane: fm.swimlane ?? t.swimlane,
            kind: fm.kind ?? t.kind,
            status: fm.status ?? t.status,
            priority: fm.priority ?? t.priority,
            appetite: fm.appetite ?? t.appetite,
            epic: fm.epic ?? t.epic,
            labels: Array.isArray(fm.labels) ? fm.labels : t.labels,
            _outcome: body,
          } : t));
        }}
      />

      <Legend
        open={legendOpen}
        onClose={() => setLegendOpen(false)}
        highlight={highlight}
        setHighlight={setHighlight}
        filterKind={tweaks.filterKind}
        setFilterKind={(v) => {
          const next = { ...tweaks, filterKind: v };
          setTweaks(next);
          window.parent?.postMessage({ type: '__edit_mode_set_keys', edits: { filterKind: v } }, '*');
        }}
        filterSwim={tweaks.filterSwim || 'all'}
        setFilterSwim={(v) => {
          const next = { ...tweaks, filterSwim: v };
          setTweaks(next);
          window.parent?.postMessage({ type: '__edit_mode_set_keys', edits: { filterSwim: v } }, '*');
        }}
        taskCounts={taskCounts}
      />

      {justCreated && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', transform: 'translateX(-50%)',
          padding: '10px 18px',
          background: '#16a34a', color: 'white',
          fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 600,
          borderRadius: 4, zIndex: 150,
          boxShadow: '0 10px 25px rgba(0,0,0,.25)',
          animation: 'fadeIn .2s ease',
        }}>
          ✓ created {justCreated} · validate-task-frontmatter.sh → ok · sync v13 → ok
        </div>
      )}
    </div>
  );
}

// global styles added imperatively
const styleEl = document.createElement('style');
styleEl.textContent = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-1px); }
    75% { transform: translateX(1px); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  .sticky-card:hover { transform: rotate(0deg) scale(1.03) !important; z-index: 5; }
  .sticky-card:active { cursor: grabbing; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: rgba(0,0,0,.04); }
  ::-webkit-scrollbar-thumb { background: rgba(0,0,0,.2); border-radius: 5px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,.35); }
`;
document.head.appendChild(styleEl);

ReactDOM.createRoot(document.getElementById('root')).render(<Board />);
