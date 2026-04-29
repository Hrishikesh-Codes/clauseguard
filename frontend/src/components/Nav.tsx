import { NavLink } from 'react-router-dom'

export default function Nav() {
  return (
    <nav className="nav">
      <a href="/" className="nav-logo">clauseguard</a>
      <div className="nav-links">
        <NavLink to="/results" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          Analysis
        </NavLink>
        <NavLink to="/history" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          History
        </NavLink>
        <NavLink to="/about" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          About
        </NavLink>
      </div>
    </nav>
  )
}
