import { NavLink } from 'react-router-dom';
import { LayoutDashboard, ListOrdered, Settings, Activity, Bot } from 'lucide-react';

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Activity size={20} color="white" />
        </div>
        <div className="sidebar-title">Minerva AI</div>
      </div>
      
      <nav className="nav-menu">
        <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </NavLink>

        <NavLink to="/assistant" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Bot size={18} />
          <span>Assistant</span>
        </NavLink>
        
        <NavLink to="/positions" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <ListOrdered size={18} />
          <span>Positions</span>
        </NavLink>
        
        <NavLink to="/configuration" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Settings size={18} />
          <span>Configuration</span>
        </NavLink>
      </nav>
    </aside>
  );
}
