import { Link, useNavigate } from 'react-router-dom';
import { Globe, LogOut, User } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import SupplyGlobe from '../components/SupplyGlobe';
import SupplyPanel from '../components/SupplyPanel';
import styles from './DashboardPage.module.css';

export default function DashboardPage() {
  const { user, setUser, supplyPoints, headquartersLocation } = useAppContext();
  const navigate = useNavigate();

  const handleLogout = () => {
    setUser(null);
    navigate('/');
  };

  return (
    <div className={styles.dashboard}>
      {/* Top bar */}
      <header className={styles.topBar}>
        <Link to="/" className={styles.logo}>
          <Globe size={22} />
          <span>Provenance</span>
        </Link>
        <div className={styles.topRight}>
          <div className={styles.userInfo}>
            <User size={16} />
            <span>{user?.name || 'User'}</span>
          </div>
          <button className={styles.logoutBtn} onClick={handleLogout}>
            <LogOut size={16} />
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className={styles.main}>
        {/* Globe area */}
        <div className={styles.globeArea}>
          <SupplyGlobe
            supplyPoints={supplyPoints}
            headquartersLocation={headquartersLocation}
          />
        </div>

        {/* Side panel */}
        <aside className={styles.sidePanel}>
          <SupplyPanel />
        </aside>
      </div>
    </div>
  );
}
