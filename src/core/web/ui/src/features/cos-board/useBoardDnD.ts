import { useState, type DragEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries } from '@/lib/hooks';
import { apiPost } from '@/lib/api-client';
import { columnWipCap } from './board-shared';
import type { UseBoardStreamReturn } from './useBoardStream';
import type { BoardConfigPayload, BoardListCard, BoardTweaks } from './types';

interface UseBoardDnDArgs {
  cfg: BoardConfigPayload | undefined;
  filtered: BoardListCard[];
  tweaks: BoardTweaks;
  pushHumanEvent: UseBoardStreamReturn['pushHumanEvent'];
  onActionError: (message: string | null) => void;
}

/**
 * Card drag-and-drop: drop-target tracking, the ready-gate + WIP pre-flight,
 * and the reposition round-trip with an opt-in forced retry.
 */
export function useBoardDnD({ cfg, filtered, tweaks, pushHumanEvent, onActionError }: UseBoardDnDArgs) {
  const qc = useQueryClient();
  const [dragging, setDragging] = useState<BoardListCard | null>(null);
  const [dragTarget, setDragTarget] = useState<string | null>(null);
  const [flashWip, setFlashWip] = useState<string | null>(null);

  const onDragStart = (e: DragEvent, task: BoardListCard) => {
    setDragging(task);
    e.dataTransfer.effectAllowed = 'move';
    try {
      e.dataTransfer.setData('text/plain', task.id);
    } catch {
      /* ignore */
    }
  };
  const onDragEnd = () => {
    setDragging(null);
    setDragTarget(null);
  };
  const onDragOver = (e: DragEvent, laneId: string, colId: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragTarget(`${laneId}:${colId}`);
  };

  const onDrop = async (e: DragEvent, laneId: string, colId: string) => {
    e.preventDefault();
    if (!dragging) return;
    if (dragging.status === colId && dragging.swimlane === laneId) return onDragEnd();

    // Ready-gate pre-flight (mirrors workflow.transition): an icebox task
    // without the 'ready' label cannot be pulled into in_progress. Surface it
    // client-side with an actionable message instead of a generic server
    // "invalid transition" after the round-trip.
    if (
      colId === 'in_progress' &&
      dragging.status === 'icebox' &&
      !(dragging.labels ?? []).includes('ready')
    ) {
      onActionError(
        `${dragging.id} is not ready — open it and "mark ready" before pulling into in_progress.`,
      );
      return onDragEnd();
    }

    const cap = columnWipCap(colId, cfg?.wip_limits);
    const inCol = filtered.filter((t) => t.status === colId && t.id !== dragging.id).length;
    if (cap != null && inCol >= cap && tweaks.showWipViolation) {
      setFlashWip(colId);
      setTimeout(() => setFlashWip(null), 1200);
    }
    onActionError(null);
    const parts: string[] = [];
    if (dragging.status !== colId) parts.push(`${dragging.status} → ${colId}`);
    if (dragging.swimlane !== laneId) parts.push(`lane ${dragging.swimlane} → ${laneId}`);
    pushHumanEvent('human-move', {
      taskId: dragging.id,
      message: parts.join(' · ') || 'no-op',
    });
    const tryMove = async (force: boolean) => {
      await apiPost('/api/board/reposition', {
        task_id: dragging.id,
        to: dragging.status === colId ? undefined : colId,
        swimlane: dragging.swimlane === laneId ? undefined : laneId,
        force,
        reason: force ? 'human drag (forced)' : undefined,
      });
      await invalidateApiQueries(qc, '/api/board/list');
      await invalidateApiQueries(qc, '/api/board/retro');
    };

    try {
      await tryMove(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'move failed';
      // If the state machine rejected this drop, offer the user an explicit
      // opt-in force retry. Anything else (network, 5xx, "task not found") is
      // surfaced as-is.
      const looksLikeInvalidTransition = /invalid transition/i.test(msg);
      if (looksLikeInvalidTransition && typeof window !== 'undefined'
          && window.confirm(
            `${msg}\n\nDrop it anyway? This will be recorded as a `
            + 'forced transition in the task history.',
          )) {
        try {
          await tryMove(true);
          pushHumanEvent('human-move', {
            taskId: dragging.id,
            message: `${parts.join(' · ')} (forced)`,
          });
          onDragEnd();
          return;
        } catch (err2) {
          const msg2 = err2 instanceof Error ? err2.message : 'force move failed';
          onActionError(msg2);
          pushHumanEvent('human-move', {
            taskId: dragging.id,
            message: `FAILED (force) — ${msg2}`,
          });
          onDragEnd();
          return;
        }
      }
      onActionError(msg);
      pushHumanEvent('human-move', { taskId: dragging.id, message: `FAILED — ${msg}` });
    }
    onDragEnd();
  };

  return { dragging, dragTarget, flashWip, onDragStart, onDragEnd, onDragOver, onDrop };
}

export type BoardDnD = ReturnType<typeof useBoardDnD>;
