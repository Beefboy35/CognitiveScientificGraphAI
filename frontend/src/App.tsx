import { useCallback, useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import './App.css'
import { AuthPage } from './features/auth/AuthPage'
import { useAuthSession } from './features/auth/model/useAuthSession'
import { GraphPage } from './features/graph/GraphPage'
import { LabPage } from './features/lab/LabPage'
import { ManagePage } from './features/manage/ManagePage'
import { WorkPage } from './features/workspace/WorkPage'
import {
  askWithEvidence,
  createPublication as createPublicationRequest,
  evaluateRagAnswer,
  getScientificGraph,
  getScientificHealth,
  listClaims,
  listPublicationChunks,
  listPublications,
  resetScientificDemo,
  searchHybrid,
  uploadPublication,
} from './shared/api/scientificKb'
import { demoQuestion, demoSearch, i18n } from './shared/i18n/dictionary'
import { useTheme } from './shared/theme/useTheme'
import type { Chunk, Claim, Evaluation, GraphData, Job, Locale, NodeFilter, Publication, RagAnswer, SearchHit, View, WorkSummary } from './shared/types/scientific-kb'

export default function App() {
  const [locale, setLocale] = useState<Locale>('ru')
  const t = i18n[locale]
  const auth = useAuthSession()
  const theme = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const view: View = location.pathname.startsWith('/lab')
    ? 'lab'
    : location.pathname.startsWith('/graph')
    ? 'graph'
    : location.pathname.startsWith('/manage')
    ? 'work'
    : 'work'
  const [summary, setSummary] = useState<WorkSummary>({})
  const [publications, setPublications] = useState<Publication[]>([])
  const [selectedPublicationId, setSelectedPublicationId] = useState('')
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [claims, setClaims] = useState<Claim[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [], summary: {} })
  const [graphFilter, setGraphFilter] = useState<NodeFilter>('all')
  const [graphSpacing, setGraphSpacing] = useState(260)
  const [graphCanvasHeight, setGraphCanvasHeight] = useState(680)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [searchQuery, setSearchQuery] = useState(demoSearch.ru)
  const [searchHits, setSearchHits] = useState<SearchHit[]>([])
  const [question, setQuestion] = useState(demoQuestion.ru)
  const [ragAnswer, setRagAnswer] = useState<RagAnswer | null>(null)
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [draftTitle, setDraftTitle] = useState('Материал')
  const [draftText, setDraftText] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const selectedPublication = publications.find((item) => item.id === selectedPublicationId)
  const selectedClaims = claims.filter((claim) => !selectedPublicationId || claim.publication_id === selectedPublicationId)
  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId)
  // brainGraph теперь строится внутри GraphPage — там же где живёт состояние
  // фильтров (limit, focus). Это даёт точечную мемоизацию.

  const refresh = useCallback(async () => {
    if (!auth.user) return
    const [health, pubs, cls, fullGraph] = await Promise.all([
      getScientificHealth(),
      listPublications(),
      listClaims(),
      getScientificGraph(),
    ])
    setSummary(health)
    setPublications(pubs)
    setClaims(cls)
    setGraph(fullGraph)
    if (!selectedPublicationId && pubs[0]) setSelectedPublicationId(pubs[0].id)
  }, [auth.user, selectedPublicationId])

  useEffect(() => {
    document.documentElement.lang = locale
    setSearchQuery((value) => (value === demoSearch.ru || value === demoSearch.en ? demoSearch[locale] : value))
    setQuestion((value) => (value === demoQuestion.ru || value === demoQuestion.en ? demoQuestion[locale] : value))
  }, [locale])

  useEffect(() => {
    if (!auth.user) return
    refresh().catch((err) => setMessage(String(err)))
  }, [auth.user, refresh])

  useEffect(() => {
    if (!auth.user || !selectedPublicationId) return
    listPublicationChunks(selectedPublicationId)
      .then((data) => setChunks(data.items))
      .catch((err) => setMessage(String(err)))
  }, [auth.user, selectedPublicationId])

  async function login(input: { email: string; password: string }) {
    setBusy(true)
    try {
      await auth.signIn(input)
      setMessage('')
    } finally {
      setBusy(false)
    }
  }

  async function register(input: { name: string; email: string; password: string; confirmPassword: string }) {
    setBusy(true)
    try {
      await auth.signUp(input)
      setMessage('')
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    void auth.signOut()
    navigate('/')
    setChunks([])
    setClaims([])
    setJobs([])
    setSearchHits([])
    setRagAnswer(null)
    setEvaluation(null)
    setSelectedPublicationId('')
  }

  async function createPublication() {
    if (draftText.trim().length < 40) {
      setMessage(t.shortText)
      return
    }
    setBusy(true)
    try {
      const response = await createPublicationRequest(draftTitle, draftText)
      setJobs((current) => [response.processing_job, ...current])
      setSelectedPublicationId(response.publication.id)
      setDraftText('')
      await refresh()
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function uploadFile(file: File | null) {
    if (!file) return
    setBusy(true)
    try {
      const response = await uploadPublication(file)
      setJobs((current) => [response.processing_job, ...current])
      setSelectedPublicationId(response.publication.id)
      await refresh()
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function resetDemo() {
    setBusy(true)
    try {
      await resetScientificDemo()
      setSearchHits([])
      setRagAnswer(null)
      setEvaluation(null)
      setMessage(t.restored)
      await refresh()
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function runSearch() {
    setBusy(true)
    try {
      const data = await searchHybrid(searchQuery)
      setSearchHits(data.items)
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function ask() {
    setBusy(true)
    try {
      const answer = await askWithEvidence(question, locale)
      setRagAnswer(answer)
      setEvaluation(null)
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function evaluate() {
    if (!ragAnswer) return
    setBusy(true)
    try {
      setEvaluation(await evaluateRagAnswer(ragAnswer.id))
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusy(false)
    }
  }

  if (!auth.isReady) {
    return <div className="app" />
  }

  if (!auth.user) {
    return (
      <div className="app">
        <AuthPage
          locale={locale}
          busy={busy}
          onLocaleChange={setLocale}
          onLogin={login}
          onRegister={register}
        />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => navigate('/')} aria-label={t.title}>KB</button>
        <nav className="tabs">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>{t.work}</NavLink>
          <NavLink to="/lab" className={({ isActive }) => (isActive ? 'active' : '')}>{t.lab}</NavLink>
          <NavLink to="/graph" className={({ isActive }) => (isActive ? 'active' : '')}>{t.graph}</NavLink>
          <NavLink to="/manage" className={({ isActive }) => (isActive ? 'active' : '')}>
            {locale === 'ru' ? 'Управление' : 'Manage'}
          </NavLink>
        </nav>
        <div className="top-actions">
          <div className="user-chip" title={auth.user.email}>
            <span>{auth.user.name}</span>
          </div>
          <button
            className="chip"
            onClick={theme.toggle}
            aria-label={t.theme}
            title={theme.theme === 'dark' ? 'Light' : 'Dark'}
          >
            {theme.theme === 'dark' ? '☀' : '☾'}
          </button>
          <button className="chip" onClick={() => setLocale(locale === 'ru' ? 'en' : 'ru')}>
            {locale === 'ru' ? 'RU' : 'EN'}
          </button>
          <button className="button ghost" disabled={busy} onClick={refresh}>{t.refresh}</button>
          <button className="button ghost" disabled={busy} onClick={logout}>{locale === 'ru' ? 'Выйти' : 'Log out'}</button>
        </div>
      </header>

      {message && <button className="toast" onClick={() => setMessage('')}>{message}</button>}

      <Routes>
        <Route
          path="/"
          element={
            <WorkPage
              t={t}
              locale={locale}
              summary={summary}
              publications={publications}
              selectedPublicationId={selectedPublicationId}
              selectedPublication={selectedPublication}
              selectedClaims={selectedClaims}
              chunks={chunks}
              jobs={jobs}
              searchQuery={searchQuery}
              searchHits={searchHits}
              question={question}
              ragAnswer={ragAnswer}
              evaluation={evaluation}
              draftTitle={draftTitle}
              draftText={draftText}
              busy={busy}
              onSelectPublication={setSelectedPublicationId}
              onDraftTitleChange={setDraftTitle}
              onDraftTextChange={setDraftText}
              onSearchQueryChange={setSearchQuery}
              onQuestionChange={setQuestion}
              onCreatePublication={createPublication}
              onUploadFile={uploadFile}
              onResetDemo={resetDemo}
              onRefresh={refresh}
              onSearch={runSearch}
              onAsk={ask}
              onEvaluate={evaluate}
            />
          }
        />
        <Route
          path="/lab"
          element={
            <LabPage
              t={t}
              locale={locale}
              defaultQuestion={question}
              defaultSearch={searchQuery}
              onError={setMessage}
            />
          }
        />
        <Route
          path="/graph"
          element={
            <GraphPage
              t={t}
              locale={locale}
              graph={graph}
              filter={graphFilter}
              spacing={graphSpacing}
              canvasHeight={graphCanvasHeight}
              selectedNodeId={selectedNodeId}
              selectedNode={selectedNode}
              onFilter={setGraphFilter}
              onSpacing={setGraphSpacing}
              onCanvasHeight={setGraphCanvasHeight}
              onSelect={setSelectedNodeId}
            />
          }
        />
        <Route path="/manage" element={<ManagePage t={t} onError={setMessage} />} />
      </Routes>
    </div>
  )
}
