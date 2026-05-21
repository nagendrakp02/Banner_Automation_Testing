import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/ui/Layout'
import DashboardPage from '@/pages/DashboardPage'
import BannersPage   from '@/pages/BannersPage'
import RunsPage      from '@/pages/RunsPage'
import RunDetailPage from '@/pages/RunDetailPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/"           element={<Navigate to="/dashboard" replace/>}/>
        <Route path="/dashboard"  element={<DashboardPage/>}/>
        <Route path="/banners"    element={<BannersPage/>}/>
        <Route path="/runs"       element={<RunsPage/>}/>
        <Route path="/runs/:runId" element={<RunDetailPage/>}/>
      </Routes>
    </Layout>
  )
}
