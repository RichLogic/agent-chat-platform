import { useCallback, useRef, useState } from 'react'
import type { Message, SharedEvent, ToolCall } from '../types/api'

// ---------------------------------------------------------------------------
// Timeline step types
// ---------------------------------------------------------------------------

type StepType =
  | 'SHOW_USER_MESSAGE'
  | 'SHOW_PLACEHOLDER'
  | 'TEXT_DELTA'
  | 'TOOL_CALL'
  | 'TOOL_RESULT'
  | 'FINALIZE'

interface TimelineStep {
  type: StepType
  messageIndex: number
  /** For TEXT_DELTA: the character(s) to append */
  content?: string
  /** For TOOL_CALL */
  toolCall?: { name: string; arguments: Record<string, unknown> }
  /** For TOOL_RESULT */
  toolResult?: { name: string; result: Record<string, unknown> }
}

const BASE_DELAYS: Record<StepType, number> = {
  SHOW_USER_MESSAGE: 400,
  SHOW_PLACEHOLDER: 200,
  TEXT_DELTA: 20,
  TOOL_CALL: 300,
  TOOL_RESULT: 500,
  FINALIZE: 300,
}

// ---------------------------------------------------------------------------
// Public state
// ---------------------------------------------------------------------------

export type ReplayStatus = 'loading' | 'ready' | 'playing' | 'paused' | 'finished'

export interface ReplayState {
  status: ReplayStatus
  displayMessages: Message[]
  progress: number
  speed: number
  messageIndex: number
  totalMessages: number
}

// ---------------------------------------------------------------------------
// Build timeline from messages + events
// ---------------------------------------------------------------------------

function buildTimeline(messages: Message[], events: SharedEvent[]): TimelineStep[] {
  const steps: TimelineStep[] = []

  // Group events by run_id
  const eventsByRun = new Map<string, SharedEvent[]>()
  for (const ev of events) {
    const list = eventsByRun.get(ev.run_id) ?? []
    list.push(ev)
    eventsByRun.set(ev.run_id, list)
  }

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i]

    if (msg.role === 'user') {
      steps.push({ type: 'SHOW_USER_MESSAGE', messageIndex: i })
      continue
    }

    // Assistant message
    steps.push({ type: 'SHOW_PLACEHOLDER', messageIndex: i })

    const runEvents = msg.run_id ? eventsByRun.get(msg.run_id) : undefined
    if (runEvents && runEvents.length > 0) {
      // Replay from actual events
      for (const ev of runEvents) {
        if (ev.type === 'text.delta') {
          const data = ev.data as { content?: string }
          if (data.content) {
            steps.push({ type: 'TEXT_DELTA', messageIndex: i, content: data.content })
          }
        } else if (ev.type === 'tool.call') {
          const data = ev.data as { name: string; arguments: Record<string, unknown> }
          steps.push({
            type: 'TOOL_CALL',
            messageIndex: i,
            toolCall: { name: data.name, arguments: data.arguments },
          })
        } else if (ev.type === 'tool.result') {
          const data = ev.data as { name: string; result: Record<string, unknown> }
          steps.push({
            type: 'TOOL_RESULT',
            messageIndex: i,
            toolResult: { name: data.name, result: data.result },
          })
        }
      }
    } else if (msg.content) {
      // No events — simulate typing from final content
      // Break content into chunks of ~3 characters for typing effect
      for (let c = 0; c < msg.content.length; c += 3) {
        steps.push({
          type: 'TEXT_DELTA',
          messageIndex: i,
          content: msg.content.slice(c, c + 3),
        })
      }
    }

    steps.push({ type: 'FINALIZE', messageIndex: i })
  }

  return steps
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useReplay(messages: Message[], events: SharedEvent[]) {
  const [status, setStatus] = useState<ReplayStatus>('ready')
  const [displayMessages, setDisplayMessages] = useState<Message[]>([])
  const [stepIndex, setStepIndex] = useState(0)
  const [speed, setSpeedState] = useState(1)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const timelineRef = useRef<TimelineStep[]>([])
  const stepIndexRef = useRef(0)
  const speedRef = useRef(1)
  const statusRef = useRef<ReplayStatus>('ready')
  const displayRef = useRef<Message[]>([])
  // Track accumulated content and tool calls per message index
  const contentAccRef = useRef<Map<number, string>>(new Map())
  const toolCallsAccRef = useRef<Map<number, ToolCall[]>>(new Map())

  // Initialize timeline lazily
  const ensureTimeline = useCallback(() => {
    if (timelineRef.current.length === 0 && messages.length > 0) {
      timelineRef.current = buildTimeline(messages, events)
    }
  }, [messages, events])

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const applyStep = useCallback(
    (step: TimelineStep) => {
      const idx = step.messageIndex
      const msg = messages[idx]

      switch (step.type) {
        case 'SHOW_USER_MESSAGE': {
          const userMsg: Message = { ...msg }
          displayRef.current = [...displayRef.current, userMsg]
          setDisplayMessages(displayRef.current)
          break
        }
        case 'SHOW_PLACEHOLDER': {
          const placeholder: Message = {
            ...msg,
            content: '',
            toolCalls: undefined,
          }
          contentAccRef.current.set(idx, '')
          toolCallsAccRef.current.set(idx, [])
          displayRef.current = [...displayRef.current, placeholder]
          setDisplayMessages(displayRef.current)
          break
        }
        case 'TEXT_DELTA': {
          const prevContent = contentAccRef.current.get(idx) ?? ''
          const newContent = prevContent + (step.content ?? '')
          contentAccRef.current.set(idx, newContent)
          const contentSnapshot = newContent
          displayRef.current = displayRef.current.map((m, i) =>
            i === displayRef.current.length - 1 && m.role === 'assistant'
              ? { ...m, content: contentSnapshot }
              : m,
          )
          setDisplayMessages(displayRef.current)
          break
        }
        case 'TOOL_CALL': {
          const prevCalls = toolCallsAccRef.current.get(idx) ?? []
          const newCalls: ToolCall[] = [
            ...prevCalls,
            {
              name: step.toolCall!.name,
              arguments: step.toolCall!.arguments,
              status: 'calling',
            },
          ]
          toolCallsAccRef.current.set(idx, newCalls)
          const callsSnapshot = [...newCalls]
          displayRef.current = displayRef.current.map((m, i) =>
            i === displayRef.current.length - 1 && m.role === 'assistant'
              ? { ...m, toolCalls: callsSnapshot }
              : m,
          )
          setDisplayMessages(displayRef.current)
          break
        }
        case 'TOOL_RESULT': {
          const calls = toolCallsAccRef.current.get(idx) ?? []
          const updatedCalls = calls.map((tc) =>
            tc.name === step.toolResult!.name && tc.status === 'calling'
              ? { ...tc, result: step.toolResult!.result, status: 'done' as const }
              : tc,
          )
          toolCallsAccRef.current.set(idx, updatedCalls)
          const callsSnapshot = [...updatedCalls]
          displayRef.current = displayRef.current.map((m, i) =>
            i === displayRef.current.length - 1 && m.role === 'assistant'
              ? { ...m, toolCalls: callsSnapshot }
              : m,
          )
          setDisplayMessages(displayRef.current)
          break
        }
        case 'FINALIZE': {
          // Set final content from the original message
          displayRef.current = displayRef.current.map((m, i) =>
            i === displayRef.current.length - 1 && m.role === 'assistant'
              ? { ...m, content: msg.content, run_id: msg.run_id }
              : m,
          )
          setDisplayMessages(displayRef.current)
          break
        }
      }
    },
    [messages],
  )

  const scheduleNext = useCallback(() => {
    const timeline = timelineRef.current
    const idx = stepIndexRef.current

    if (idx >= timeline.length) {
      setStatus('finished')
      statusRef.current = 'finished'
      return
    }

    const step = timeline[idx]
    const delay = BASE_DELAYS[step.type] / speedRef.current

    timerRef.current = setTimeout(() => {
      applyStep(step)
      stepIndexRef.current = idx + 1
      setStepIndex(idx + 1)

      if (statusRef.current === 'playing') {
        scheduleNext()
      }
    }, delay)
  }, [applyStep])

  const play = useCallback(() => {
    ensureTimeline()
    if (statusRef.current === 'finished') {
      // Restart
      stepIndexRef.current = 0
      setStepIndex(0)
      displayRef.current = []
      setDisplayMessages([])
      contentAccRef.current.clear()
      toolCallsAccRef.current.clear()
    }
    setStatus('playing')
    statusRef.current = 'playing'
    scheduleNext()
  }, [ensureTimeline, scheduleNext])

  const pause = useCallback(() => {
    clearTimer()
    setStatus('paused')
    statusRef.current = 'paused'
  }, [clearTimer])

  const setSpeed = useCallback(
    (s: number) => {
      speedRef.current = s
      setSpeedState(s)
      // If playing, restart scheduling with new speed
      if (statusRef.current === 'playing') {
        clearTimer()
        scheduleNext()
      }
    },
    [clearTimer, scheduleNext],
  )

  const restart = useCallback(() => {
    clearTimer()
    stepIndexRef.current = 0
    setStepIndex(0)
    displayRef.current = []
    setDisplayMessages([])
    contentAccRef.current.clear()
    toolCallsAccRef.current.clear()
    setStatus('ready')
    statusRef.current = 'ready'
  }, [clearTimer])

  // Compute which message index we're currently on
  const timeline = timelineRef.current
  const currentStep = timeline[Math.min(stepIndex, timeline.length - 1)]
  const messageIndex = currentStep?.messageIndex ?? 0

  const progress = timeline.length > 0 ? stepIndex / timeline.length : 0

  return {
    status,
    displayMessages,
    progress,
    speed,
    messageIndex,
    totalMessages: messages.length,
    play,
    pause,
    setSpeed,
    restart,
  }
}
