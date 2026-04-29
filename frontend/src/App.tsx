import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AnalysisProvider } from './context/AnalysisContext'
import Landing from './pages/Landing'
import Results from './pages/Results'
import History from './pages/History'
import About from './pages/About'

export default function App() {
  return (
    <AnalysisProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/results" element={<Results />} />
          <Route path="/history" element={<History />} />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AnalysisProvider>
  )
}
