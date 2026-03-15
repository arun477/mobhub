import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import ExplorePage from './components/ExplorePage'
import HubDetail from './components/HubDetail'
import AgentPanel from './components/AgentPanel'
import { LayoutGrid, Plus } from 'lucide-react'

export default function App() {
  const navigate = useNavigate()
  const loc = useLocation()

  const isHub = loc.pathname.startsWith('/hubs/')
  const isExplore = loc.pathname === '/' || loc.pathname.startsWith('/hubs')
  const isCreate = loc.pathname.startsWith('/create')

  return (
    <>
      <nav className="global-rail">
        <div className="rail-brand" onClick={() => navigate('/')}>
          <svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 2L28.5 9V23L16 30L3.5 23V9L16 2Z" stroke="url(#mh-grad)" strokeWidth="2" fill="none" />
            <path d="M9 22V11L13 17L16 13" stroke="#00e5ff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
            <path d="M18 11V22M23 11V22M18 16.5H23" stroke="#ff2d78" strokeWidth="2.2" strokeLinecap="round" fill="none" />
            <circle cx="16" cy="2" r="1.5" fill="#00e5ff" />
            <circle cx="28.5" cy="9" r="1.5" fill="#ff2d78" />
            <circle cx="3.5" cy="9" r="1.5" fill="#00e5ff" />
            <defs>
              <linearGradient id="mh-grad" x1="3.5" y1="2" x2="28.5" y2="30">
                <stop stopColor="#00e5ff" />
                <stop offset="1" stopColor="#ff2d78" />
              </linearGradient>
            </defs>
          </svg>
        </div>

        <div className="rail-top-links">
          <div
            className={`rail-link ${isExplore && !isHub ? 'active' : ''}`}
            onClick={() => navigate('/')}
            data-tooltip="Explore"
          >
            <LayoutGrid size={18} strokeWidth={1.8} />
          </div>
          <div
            className={`rail-link ${isCreate ? 'active' : ''}`}
            onClick={() => navigate('/create')}
            data-tooltip="Create Hub"
          >
            <Plus size={18} strokeWidth={1.8} />
          </div>
        </div>
      </nav>

      <div className="app-content">
        <Routes>
          <Route path="/" element={<ExplorePage />} />
          <Route path="/hubs/:id" element={<HubDetail />} />
          <Route path="/create" element={<AgentPanel />} />
          <Route path="/agent" element={<Navigate to="/create" />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
    </>
  )
}
