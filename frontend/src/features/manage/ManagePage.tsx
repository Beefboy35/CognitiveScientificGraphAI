import { useCallback, useEffect, useState } from 'react'

import {
  deletePublication,
  exportGraphJson,
  exportSearchCsvUrl,
  listPublications,
  listReviewQueue,
  listRagAnswers,
  resolveReviewItem,
} from '../../shared/api/scientificKb'
import type { Labels } from '../../shared/i18n/dictionary'
import type { Publication, RagAnswer, ReviewItem } from '../../shared/types/scientific-kb'

type Props = {
  t: Labels
  onError: (message: string) => void
}

export function ManagePage({ t, onError }: Props) {
  const [tab, setTab] = useState<'library' | 'review' | 'history' | 'export'>('library')
  const [publications, setPublications] = useState<Publication[]>([])
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([])
  const [history, setHistory] = useState<RagAnswer[]>([])
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [pubs, review, hist] = await Promise.all([
        listPublications(),
        listReviewQueue().then((r) => r.items),
        listRagAnswers(),
      ])
      setPublications(pubs)
      setReviewItems(review)
      setHistory(hist)
    } catch (err) {
      onError(String(err))
    }
  }, [onError])

  useEffect(() => {
    refresh().catch(() => undefined)
  }, [refresh])

  const onDeletePublication = useCallback(
    async (id: string) => {
      if (!window.confirm('Удалить публикацию? Это действие необратимо.')) return
      setBusy(true)
      try {
        await deletePublication(id)
        await refresh()
      } catch (err) {
        onError(String(err))
      } finally {
        setBusy(false)
      }
    },
    [onError, refresh],
  )

  const onResolve = useCallback(
    async (id: string, action: 'approve' | 'reject') => {
      setBusy(true)
      try {
        await resolveReviewItem(id, action)
        await refresh()
      } catch (err) {
        onError(String(err))
      } finally {
        setBusy(false)
      }
    },
    [onError, refresh],
  )

  const downloadGraph = useCallback(async () => {
    try {
      const data = await exportGraphJson()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `graph_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      onError(String(err))
    }
  }, [onError])

  const downloadSearchCsv = useCallback(async () => {
    const query = window.prompt('Поисковый запрос для экспорта:', 'двоичный поиск')
    if (!query) return
    try {
      const { url, body } = exportSearchCsvUrl(query, 30)
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: localStorage.getItem('kb.auth.access_token')
            ? `Bearer ${localStorage.getItem('kb.auth.access_token')}`
            : '',
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const dl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = dl
      a.download = `search_${Date.now()}.csv`
      a.click()
      URL.revokeObjectURL(dl)
    } catch (err) {
      onError(String(err))
    }
  }, [onError])

  return (
    <div className="lab-page">
      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.materials} · {t.review}</h2>
          <div className="lab-toolbar">
            {(['library', 'review', 'history', 'export'] as const).map((id) => (
              <button
                key={id}
                type="button"
                className={`chip ${id === tab ? 'active' : ''}`}
                onClick={() => setTab(id)}
              >
                {id === 'library' && t.library}
                {id === 'review' && t.reviewQueue}
                {id === 'history' && (t.title === 'Scientific Base' ? 'History' : 'История')}
                {id === 'export' && (t.title === 'Scientific Base' ? 'Export' : 'Экспорт')}
              </button>
            ))}
          </div>
        </header>

        {tab === 'library' && (
          <ul className="lab-review scrollable">
            {publications.length === 0 && <li className="empty-state">{t.emptyFragments}</li>}
            {publications.map((pub) => (
              <li className="lab-review-item" key={pub.id}>
                <header>
                  <strong>{pub.title}</strong>
                  <span className="muted">{pub.year ?? ''} · {pub.status}</span>
                </header>
                <p className="muted">{pub.abstract?.slice(0, 240) ?? ''}</p>
                <div className="chips">
                  {pub.metadata?.research_field && (
                    <span className="tag violet">{pub.metadata.research_field}</span>
                  )}
                  {(pub.authors || []).slice(0, 3).map((a) => (
                    <span className="tag" key={a}>{a}</span>
                  ))}
                </div>
                <div className="lab-toolbar">
                  <button
                    className="button ghost"
                    disabled={busy}
                    onClick={() => onDeletePublication(pub.id)}
                  >
                    {t.title === 'Scientific Base' ? 'Delete' : 'Удалить'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {tab === 'review' && (
          <>
            {reviewItems.length === 0 ? (
              <div className="empty-state">{t.noReviewItems}</div>
            ) : (
              <ul className="lab-review scrollable">
                {reviewItems.map((item) => (
                  <li className="lab-review-item" key={item.id}>
                    <header>
                      <strong>{item.item_type}</strong>
                      <span className="muted">{item.item_id}</span>
                    </header>
                    <p>{item.reason}</p>
                    <div className="lab-toolbar">
                      <button className="button ghost" disabled={busy} onClick={() => onResolve(item.id, 'approve')}>
                        {t.approve}
                      </button>
                      <button className="button ghost" disabled={busy} onClick={() => onResolve(item.id, 'reject')}>
                        {t.reject}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {tab === 'history' && (
          <ul className="lab-review scrollable">
            {history.length === 0 && <li className="empty-state">{t.emptyAnswer}</li>}
            {history.map((rag) => (
              <li className="lab-review-item" key={rag.id}>
                <header>
                  <strong>{rag.question}</strong>
                  <span className={`tag ${rag.status === 'answered' ? 'success' : 'warn'}`}>
                    {rag.status}
                  </span>
                </header>
                <p className="muted">{rag.answer.slice(0, 320)}</p>
                <div className="chips">
                  <span className="tag">confidence {rag.confidence_score.toFixed(2)}</span>
                  <span className="tag">{rag.sources?.length ?? 0} sources</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {tab === 'export' && (
          <div className="lab-toolbar">
            <button className="button" disabled={busy} onClick={downloadGraph}>
              {t.title === 'Scientific Base' ? 'Download graph (JSON)' : 'Скачать граф (JSON)'}
            </button>
            <button className="button ghost" disabled={busy} onClick={downloadSearchCsv}>
              {t.title === 'Scientific Base' ? 'Download search results (CSV)' : 'Экспорт поиска (CSV)'}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
