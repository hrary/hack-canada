import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import styles from './AuthPage.module.css';

export default function SignupPage() {
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { setUser } = useAppContext();
  const navigate = useNavigate();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    // Mock signup — replace with real auth
    setUser({ email, name, company });
    navigate('/dashboard');
  };

  return (
    <div className={styles.page}>
      <div className={styles.bgGlow} />
      <motion.div
        className={styles.card}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <Link to="/" className={styles.backLink}>
          <ArrowLeft size={16} /> Back to home
        </Link>
        <h1 className={styles.title}>Create account</h1>
        <p className={styles.subtitle}>Start mapping your supply chain today.</p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label}>Full Name</label>
            <input
              className={styles.input}
              type="text"
              placeholder="Your name"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Company</label>
            <input
              className={styles.input}
              type="text"
              placeholder="Your company"
              value={company}
              onChange={e => setCompany(e.target.value)}
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Email</label>
            <input
              className={styles.input}
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Password</label>
            <input
              className={styles.input}
              type="password"
              placeholder="Create a password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <button type="submit" className={styles.submitBtn}>Create Account</button>
        </form>

        <p className={styles.footer}>
          Already have an account?
          <Link to="/login" className={styles.footerLink}>Sign in</Link>
        </p>
      </motion.div>
    </div>
  );
}
