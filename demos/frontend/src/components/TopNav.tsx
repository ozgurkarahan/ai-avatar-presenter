import React from 'react';
import { NavLink } from 'react-router-dom';

const tabStyle: React.CSSProperties = {
  color: 'rgba(255,255,255,0.85)', textDecoration: 'none',
  padding: '8px 14px', borderRadius: '8px', fontSize: '14px', fontWeight: 600,
  transition: 'background 0.15s',
};
const activeStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.18)', color: 'white' };

export default function TopNav() {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #003366 0%, #005599 100%)',
      padding: '10px 32px', display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <div style={{ color: 'white', fontWeight: 800, fontSize: 15, letterSpacing: 0.5 }}>
        Saint-Gobain · AI Avatar Suite
      </div>
      <nav style={{ display: 'flex', gap: '4px', marginLeft: '24px' }}>
        <NavLink to="/" end style={({ isActive }) => ({ ...tabStyle, ...(isActive ? activeStyle : {}) })}>
          🎙️ Presenter
        </NavLink>
        <NavLink to="/podcast" end style={({ isActive }) => ({ ...tabStyle, ...(isActive ? activeStyle : {}) })}>
          🎧 Podcast
        </NavLink>
        <NavLink to="/podcast/library" style={({ isActive }) => ({ ...tabStyle, ...(isActive ? activeStyle : {}) })}>
          📚 Library
        </NavLink>
      </nav>
    </div>
  );
}
