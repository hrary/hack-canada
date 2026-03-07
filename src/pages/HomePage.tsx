import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Globe, ArrowRight, Shield, Zap, BarChart3, ChevronRight } from 'lucide-react';
import styles from './HomePage.module.css';

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.15, duration: 0.6, ease: 'easeOut' as const },
  }),
};

export default function HomePage() {
  return (
    <div className={styles.page}>
      {/* Ambient background effects */}
      <div className={styles.bgGlow1} />
      <div className={styles.bgGlow2} />
      <div className={styles.gridOverlay} />

      {/* Navbar */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <Link to="/" className={styles.logo}>
            <Globe size={28} />
            <span>Provenance</span>
          </Link>
          <div className={styles.navLinks}>
            <Link to="/login" className={styles.navLink}>Log In</Link>
            <Link to="/signup" className={styles.navCta}>
              Get Started <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className={styles.hero}>
        <motion.div
          className={styles.heroContent}
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.15 } } }}
        >
          <motion.div className={styles.badge} variants={fadeUp} custom={0}>
            <Zap size={14} />
            Supply Chain Intelligence Platform
          </motion.div>
          <motion.h1 className={styles.heroTitle} variants={fadeUp} custom={1}>
            Visualize Your Global<br />
            <span className="gradient-text">Supply Chain</span>
          </motion.h1>
          <motion.p className={styles.heroSubtitle} variants={fadeUp} custom={2}>
            Map every supplier, trace every material, and gain unprecedented
            visibility into your entire supply network on an interactive 3D globe.
          </motion.p>
          <motion.div className={styles.heroCtas} variants={fadeUp} custom={3}>
            <Link to="/signup" className={styles.ctaPrimary}>
              Start Mapping <ArrowRight size={18} />
            </Link>
            <Link to="/login" className={styles.ctaSecondary}>
              Sign In <ChevronRight size={18} />
            </Link>
          </motion.div>
        </motion.div>

        {/* Hero globe illustration */}
        <motion.div
          className={styles.heroVisual}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5, duration: 0.8 }}
        >
          <div className={styles.globePreview}>
            <div className={styles.globeRing} />
            <div className={styles.globeRing2} />
            <Globe size={120} strokeWidth={0.8} className={styles.globeIcon} />
          </div>
        </motion.div>
      </section>

      {/* Features */}
      <section className={styles.features}>
        <motion.div
          className={styles.featuresGrid}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-100px' }}
          variants={{ visible: { transition: { staggerChildren: 0.1 } } }}
        >
          {[
            { icon: <Globe size={24} />, title: 'Interactive 3D Globe', desc: 'Visualize your entire supply network on a stunning interactive globe with real-time data mapping.' },
            { icon: <Shield size={24} />, title: 'Risk Assessment', desc: 'Identify potential vulnerabilities and single points of failure across your supply chain.' },
            { icon: <BarChart3 size={24} />, title: 'Analytics Dashboard', desc: 'Comprehensive insights and analytics to optimize your sourcing and logistics decisions.' },
          ].map((feature, i) => (
            <motion.div key={i} className={styles.featureCard} variants={fadeUp} custom={i}>
              <div className={styles.featureIcon}>{feature.icon}</div>
              <h3>{feature.title}</h3>
              <p>{feature.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerBrand}>
            <Globe size={20} />
            <span>Provenance</span>
          </div>
          <p>&copy; 2026 Provenance. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
