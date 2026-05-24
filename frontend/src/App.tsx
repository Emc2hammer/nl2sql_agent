import React, { useState, useEffect, useRef } from 'react'
import { sendChat, getSchema, healthCheck, type ChatResponse, type TableSchema, type HealthStatus } from './api'

/** Format JSON safely for display. */
function formatJSON(data: any): string {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

/** Main App component. */
export default function App() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<ChatResponse | null>(null)
  const [schema, setSchema] = useState<TableSchema | null>(null)
  const [showSchema, setShowSchema] = useState(false)
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [healthData, setHealthData] = useState<HealthStatus | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    healthCheck()
      .then(data => {
        setBackendStatus('online')
        setHealthData(data)
      })
      .catch(() => setBackendStatus('offline'))
  }, [])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px'
    }
  }, [question])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim() || loading) return

    setLoading(true)
    setResponse(null)

    try {
      const res = await sendChat({ question: question.trim() })
      setResponse(res)
    } catch (err: any) {
      setResponse({
        trace_id: '',
        question: question.trim(),
        sql: '',
        generated_sql: '',
        result: [],
        columns: [],
        execution_time: 0,
        error: err.message || 'Unknown error',
        explanation: '',
        insights: [],
      })
    } finally {
      setLoading(false)
    }
  }

  const handleLoadSchema = async () => {
    setShowSchema(!showSchema)
    if (!schema) {
      try {
        const s = await getSchema()
        setSchema(s)
      } catch {
        // Keep the chat usable even if schema preview fails.
      }
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div style={styles.headerContent}>
          <h1 style={styles.title}>AskData</h1>
          <p style={styles.subtitle}>用自然语言查询制造业数据集</p>
          <div style={styles.statusRow}>
            <span style={{
              ...styles.statusDot,
              backgroundColor: backendStatus === 'online' ? '#22c55e'
                : backendStatus === 'offline' ? '#ef4444' : '#f59e0b',
            }} />
            <span style={styles.statusText}>
              {backendStatus === 'online' ? '后端已连接'
                : backendStatus === 'offline' ? '后端离线'
                : '正在检查连接...'}
            </span>
            {healthData && (
              <div style={styles.modelBadges}>
                <span style={{
                  ...styles.modelBadge,
                  borderColor: healthData.models.llm.connected ? '#22c55e' : '#ef4444',
                }} title={healthData.models.llm.model}>
                  LLM
                </span>
                <span style={{
                  ...styles.modelBadge,
                  borderColor: healthData.models.embedding.connected ? '#22c55e' : '#ef4444',
                }} title={healthData.models.embedding.model}>
                  Emb
                </span>
                <span style={{
                  ...styles.modelBadge,
                  borderColor: healthData.models.reranker.loaded ? '#22c55e' : '#f59e0b',
                }} title={healthData.models.reranker.model}>
                  Rank
                </span>
              </div>
            )}
            <button
              onClick={handleLoadSchema}
              style={styles.schemaBtn}
            >
              {showSchema ? '收起 Schema' : '查看 Schema'}
            </button>
          </div>
        </div>
      </header>

      {showSchema && (
        <div style={styles.schemaPanel}>
          <h3 style={styles.schemaTitle}>数据库 Schema</h3>
          {schema ? (
            <pre style={styles.schemaCode}>
              {JSON.stringify(schema, null, 2)}
            </pre>
          ) : (
            <p style={styles.loadingSchema}>加载中...</p>
          )}
        </div>
      )}

      <main style={styles.main}>
        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.inputWrapper}>
            <textarea
              ref={textareaRef}
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入你的问题，例如：显示最近 10 个订单"
              rows={1}
              style={styles.textarea}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              style={{
                ...styles.sendBtn,
                opacity: loading || !question.trim() ? 0.5 : 1,
                cursor: loading || !question.trim() ? 'not-allowed' : 'pointer',
              }}
              title="发送"
            >
              {loading ? (
                <span style={styles.spinner} />
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" />
                </svg>
              )}
            </button>
          </div>
          <p style={styles.hint}>按 Enter 发送，Shift + Enter 换行</p>
        </form>

        {response && (
          <div style={styles.resultCard}>
            <div style={styles.resultSection}>
              <div style={styles.sectionLabel}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" />
                </svg>
                问题
              </div>
              <p style={styles.questionText}>{response.question}</p>
            </div>

            {(response.generated_sql || response.sql) && (
              <div style={styles.resultSection}>
                <div style={styles.sectionLabel}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M4 17l6-6-6-6" /><path d="M12 19h8" />
                  </svg>
                  生成的 SQL
                </div>
                <pre style={styles.sqlCode}><code>{response.generated_sql || response.sql}</code></pre>
              </div>
            )}

            {response.explanation && (
              <div style={styles.resultSection}>
                <div style={styles.sectionLabel}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" />
                  </svg>
                  生成说明
                </div>
                <pre style={styles.explanationText}>{response.explanation}</pre>
              </div>
            )}

            {response.error && (
              <div style={styles.resultSection}>
                <div style={{ ...styles.sectionLabel, color: '#ef4444' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" /><path d="M15 9l-6 6" /><path d="M9 9l6 6" />
                  </svg>
                  错误
                </div>
                <pre style={styles.errorText}>{response.error}</pre>
              </div>
            )}

            {response.columns.length > 0 && !response.error && (
              <div style={styles.resultSection}>
                <div style={styles.sectionLabel}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /><path d="M9 21V9" />
                  </svg>
                  查询结果
                  <span style={styles.meta}>
                    {(Array.isArray(response.result) ? response.result.length : 0)} 行，用时 {response.execution_time}s
                  </span>
                </div>
                <div style={styles.tableWrapper}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        {response.columns.map(col => (
                          <th key={col} style={styles.th}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.isArray(response.result) && response.result.map((row, i) => (
                        <tr key={i} style={i % 2 === 0 ? undefined : styles.rowAlt}>
                          {response.columns.map(col => (
                            <td key={col} style={styles.td}>
                              {row[col] !== null && row[col] !== undefined ? String(row[col]) : 'NULL'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {response.execution_time > 0 && (response.columns.length === 0 || response.error) && (
              <p style={styles.execTime}>执行时间：{response.execution_time}s</p>
            )}

            <div style={styles.resultSection}>
              <div style={styles.sectionLabel}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
                </svg>
                原始 JSON
              </div>
              <pre style={styles.schemaCode}>
                {formatJSON({
                  trace_id: response.trace_id,
                  generated_sql: response.generated_sql || response.sql,
                  result: response.result,
                  explanation: response.explanation || '',
                  insights: response.insights || [],
                })}
              </pre>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

/** Inline styles. */
const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#0f172a',
    color: '#e2e8f0',
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
  },
  header: {
    borderBottom: '1px solid #1e293b',
    background: 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)',
  },
  headerContent: {
    maxWidth: '800px',
    margin: '0 auto',
    padding: '32px 24px 24px',
  },
  title: {
    fontSize: '28px',
    fontWeight: 700,
    margin: 0,
    background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  subtitle: {
    fontSize: '14px',
    color: '#94a3b8',
    margin: '4px 0 16px',
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  statusText: {
    fontSize: '13px',
    color: '#94a3b8',
  },
  schemaBtn: {
    marginLeft: 'auto',
    background: 'transparent',
    border: '1px solid #334155',
    color: '#94a3b8',
    padding: '4px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '12px',
  },
  modelBadges: {
    display: 'flex',
    gap: '4px',
    marginLeft: '8px',
  },
  modelBadge: {
    fontSize: '10px',
    padding: '2px 6px',
    borderRadius: '4px',
    border: '1px solid #334155',
    color: '#94a3b8',
    fontWeight: 600,
    letterSpacing: '0.5px',
    cursor: 'help',
  },
  schemaPanel: {
    maxWidth: '800px',
    margin: '0 auto',
    padding: '0 24px',
  },
  schemaTitle: {
    fontSize: '14px',
    fontWeight: 600,
    color: '#94a3b8',
    margin: '12px 0 8px',
  },
  schemaCode: {
    background: '#1e293b',
    borderRadius: '8px',
    padding: '16px',
    fontSize: '12px',
    overflow: 'auto',
    maxHeight: '300px',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  },
  loadingSchema: {
    color: '#64748b',
    fontSize: '13px',
  },
  main: {
    maxWidth: '800px',
    margin: '0 auto',
    padding: '24px',
  },
  form: {
    marginBottom: '24px',
  },
  inputWrapper: {
    display: 'flex',
    gap: '8px',
    alignItems: 'flex-end',
    background: '#1e293b',
    borderRadius: '12px',
    padding: '8px',
    border: '1px solid #334155',
  },
  textarea: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    color: '#e2e8f0',
    fontSize: '14px',
    padding: '8px',
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
    lineHeight: '1.5',
    minHeight: '24px',
    maxHeight: '200px',
  },
  sendBtn: {
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    border: 'none',
    background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
    color: 'white',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  spinner: {
    width: '18px',
    height: '18px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.6s linear infinite',
    display: 'inline-block',
  },
  hint: {
    fontSize: '12px',
    color: '#475569',
    margin: '6px 0 0 4px',
  },
  resultCard: {
    background: '#1e293b',
    borderRadius: '12px',
    border: '1px solid #334155',
    overflow: 'hidden',
  },
  resultSection: {
    padding: '16px',
    borderBottom: '1px solid #334155',
  },
  sectionLabel: {
    fontSize: '13px',
    fontWeight: 600,
    color: '#60a5fa',
    marginBottom: '8px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  questionText: {
    fontSize: '15px',
    lineHeight: '1.6',
    margin: 0,
    color: '#f1f5f9',
  },
  sqlCode: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '12px',
    fontSize: '13px',
    overflow: 'auto',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    color: '#a5f3fc',
    margin: 0,
  },
  errorText: {
    background: '#1e1b1b',
    borderRadius: '8px',
    padding: '12px',
    fontSize: '13px',
    overflow: 'auto',
    color: '#fca5a5',
    margin: 0,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  },
  explanationText: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '12px',
    fontSize: '13px',
    overflow: 'auto',
    color: '#cbd5e1',
    margin: 0,
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
    whiteSpace: 'pre-wrap',
    lineHeight: '1.6',
  },
  meta: {
    marginLeft: 'auto',
    fontWeight: 400,
    fontSize: '12px',
    color: '#64748b',
  },
  tableWrapper: {
    overflow: 'auto',
    borderRadius: '8px',
    border: '1px solid #334155',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '13px',
  },
  th: {
    background: '#0f172a',
    padding: '10px 12px',
    textAlign: 'left' as const,
    fontWeight: 600,
    color: '#94a3b8',
    borderBottom: '1px solid #334155',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '8px 12px',
    borderBottom: '1px solid #1e293b',
    color: '#cbd5e1',
  },
  rowAlt: {
    backgroundColor: '#172033',
  },
  execTime: {
    padding: '12px 16px',
    fontSize: '12px',
    color: '#64748b',
    margin: 0,
  },
}
