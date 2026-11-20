import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Queue from './pages/Queue'
import Editor from './pages/Editor'
import History from './pages/History'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        <header className="nav">
          <div className="nav-brand">Horizn</div>
          <nav className="nav-links">
            <NavLink
              to="/"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              Queue
            </NavLink>
            <NavLink
              to="/history"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              Published
            </NavLink>
          </nav>
        </header>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Queue />} />
            <Route path="/editor/:id" element={<Editor />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
