import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Stocks from './pages/Stocks'
import StockDetail from './pages/StockDetail'
import Predictions from './pages/Predictions'
import PredictionDetail from './pages/PredictionDetail'
import Admin from './pages/Admin'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/stocks" element={<Stocks />} />
        <Route path="/stocks/:ticker" element={<StockDetail />} />
        <Route path="/predictions" element={<Predictions />} />
        <Route path="/predictions/:ticker" element={<Predictions />} />
        <Route path="/predictions/id/:id" element={<PredictionDetail />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Layout>
  )
}
