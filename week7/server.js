// node server.js
import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import cookieParser from 'cookie-parser';
import rateLimit from 'express-rate-limit';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { Sequelize, DataTypes, Op } from 'sequelize';

// -----------------------------
// Config
// -----------------------------
const app = express();
const PORT = process.env.PORT || 5000;
const JWT_SECRET = process.env.JWT_SECRET || 'CHANGE_ME';
const ACCESS_EXPIRES_MIN = parseInt(process.env.ACCESS_EXPIRES_MIN || '15', 10);
const REFRESH_EXPIRES_DAYS = parseInt(process.env.REFRESH_EXPIRES_DAYS || '14', 10);

const corsOrigins = (process.env.CORS_ORIGINS || 'http://localhost:3000')
  .split(',')
  .map(s => s.trim());

app.use(helmet());
app.use(cors({ origin: corsOrigins, credentials: true }));
app.use(express.json());
app.use(cookieParser());

// Rate limit (auth endpoints chặt hơn)
const limiter = rateLimit({ windowMs: 60 * 1000, max: 300 }); // 300 req/phút
app.use(limiter);
const authLimiter = rateLimit({ windowMs: 60 * 1000, max: 20 });

// -----------------------------
// DB (SQLite via Sequelize)
// -----------------------------
const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: 'library.sqlite',
  logging: false
});

// Models cũ
const Book = sequelize.define('Book', {
  title: { type: DataTypes.STRING, allowNull: false },
  author: { type: DataTypes.STRING, allowNull: false },
  stock: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 }
});

const Member = sequelize.define('Member', {
  name: { type: DataTypes.STRING, allowNull: false },
  email: { type: DataTypes.STRING, unique: true, allowNull: false }
});

const Loan = sequelize.define('Loan', {
  // dùng CURRENT_TIMESTAMP để tránh lỗi cú pháp SQLite
  loan_date: { 
    type: DataTypes.DATE, 
    allowNull: false, 
    defaultValue: Sequelize.literal('CURRENT_TIMESTAMP') 
  },
  return_date: { type: DataTypes.DATE, allowNull: true }
});
Loan.belongsTo(Book, { foreignKey: { allowNull: false } });
Loan.belongsTo(Member, { foreignKey: { allowNull: false } });

// Auth models
const Role = sequelize.define('Role', { name: { type: DataTypes.STRING(32), unique: true }});
const User = sequelize.define('User', {
  email: { type: DataTypes.STRING, unique: true, allowNull: false },
  password_hash: { type: DataTypes.STRING, allowNull: false },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true }
});
const UserRole = sequelize.define('UserRole', {});
User.belongsToMany(Role, { through: UserRole });
Role.belongsToMany(User, { through: UserRole });

const TokenBlocklist = sequelize.define('TokenBlocklist', {
  jti: { type: DataTypes.STRING(64), unique: true, allowNull: false },
  reason: { type: DataTypes.STRING(64) }
});

// -----------------------------
// Helpers JWT
// -----------------------------
function signAccessToken(payload) {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: `${ACCESS_EXPIRES_MIN}m` });
}
function signRefreshToken(payload) {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: `${REFRESH_EXPIRES_DAYS}d` });
}
function setRefreshCookie(res, token) {
  res.cookie('refresh_token', token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: REFRESH_EXPIRES_DAYS * 24 * 60 * 60 * 1000
  });
}
async function isRevoked(jti) {
  const t = await TokenBlocklist.findOne({ where: { jti } });
  return !!t;
}
async function revokeJti(jti, reason='manual') {
  try { await TokenBlocklist.create({ jti, reason }); } catch {}
}
function getJti(token) {
  // decode without verify (ok cho lấy jti; không dùng dữ liệu nhạy cảm từ đây)
  const decoded = jwt.decode(token, { complete: true });
  return decoded?.header?.jti || decoded?.payload?.jti || null;
}

// Middleware: require access token
function requireAuth(req, res, next) {
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  if (!token) return res.status(401).json({ message: 'Missing token' });
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.user = payload; // { sub, roles, ... }
    next();
  } catch {
    return res.status(401).json({ message: 'Invalid/expired token' });
  }
}
function requireRoles(...accepted) {
  return (req, res, next) => {
    if (!req.user) return res.status(401).json({ message: 'Unauthenticated' });
    const have = new Set(req.user.roles || []);
    const ok = accepted.every(r => have.has(r));
    if (!ok) return res.status(403).json({ message: 'Insufficient role' });
    next();
  };
}

// -----------------------------
// Auth routes
// -----------------------------
app.post('/auth/register', authLimiter, async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ message: 'email/password required' });
  const exists = await User.findOne({ where: { email: email.toLowerCase() } });
  if (exists) return res.status(409).json({ message: 'email exists' });

  const password_hash = await bcrypt.hash(password, 10);
  const user = await User.create({ email: email.toLowerCase(), password_hash });

  const member = await Role.findOrCreate({ where: { name: 'member' }, defaults: { name: 'member' }});
  await user.addRole(member[0]);

  return res.status(201).json({ message: 'ok' });
});

app.post('/auth/login', authLimiter, async (req, res) => {
  const { email, password } = req.body || {};
  const user = await User.findOne({ where: { email: (email||'').toLowerCase() }, include: Role });
  if (!user || !user.is_active) return res.status(401).json({ message: 'invalid credentials' });
  const ok = await bcrypt.compare(password || '', user.password_hash);
  if (!ok) return res.status(401).json({ message: 'invalid credentials' });

  const roles = user.Roles.map(r => r.name);
  const access_token = signAccessToken({ sub: user.id, roles, typ: 'access' });
  const refresh_token = signRefreshToken({ sub: user.id, typ: 'refresh' });

  setRefreshCookie(res, refresh_token);
  return res.json({ access_token });
});

app.post('/auth/refresh', async (req, res) => {
  const token = req.cookies?.refresh_token;
  if (!token) return res.status(401).json({ message: 'Missing refresh token' });

  try {
    const payload = jwt.verify(token, JWT_SECRET); // verify
    const jti = getJti(token) || token;            // dùng raw token làm chìa nếu không có jti
    if (await isRevoked(jti)) return res.status(401).json({ message: 'Refresh revoked' });

    // rotate: revoke cũ
    await revokeJti(jti, 'rotated');

    const user = await User.findByPk(payload.sub, { include: Role });
    if (!user || !user.is_active) return res.status(403).json({ message: 'User inactive' });

    const roles = user.Roles.map(r => r.name);
    const newAccess = signAccessToken({ sub: user.id, roles, typ: 'access' });
    const newRefresh = signRefreshToken({ sub: user.id, typ: 'refresh' });

    setRefreshCookie(res, newRefresh);
    return res.json({ access_token: newAccess });
  } catch {
    return res.status(401).json({ message: 'Invalid refresh' });
  }
});

app.post('/auth/logout', async (req, res) => {
  const token = req.cookies?.refresh_token;
  if (token) {
    const jti = getJti(token) || token;
    await revokeJti(jti, 'logout');
  }
  res.clearCookie('refresh_token', { httpOnly: true, sameSite: 'lax', secure: process.env.NODE_ENV === 'production' });
  return res.json({ message: 'logged out' });
});

app.get('/auth/me', requireAuth, async (req, res) => {
  return res.json({ user_id: req.user.sub, roles: req.user.roles || [] });
});

// -----------------------------
// Utils pagination (giữ logic tối giản; nếu trước bạn có tham số khác thì thay vào)
// -----------------------------
function getOffsetLimit(req, def = 20, max = 100) {
  const offset = Math.max(parseInt(req.query.offset || '0', 10) || 0, 0);
  const limit = Math.min(parseInt(req.query.limit || `${def}`, 10) || def, max);
  return { offset, limit };
}

// -----------------------------
// API cũ: Books / Members / Loans
// (GET giữ public; thao tác ghi yêu cầu admin)
// -----------------------------

// Books
app.get('/api/v1/books', async (req, res) => {
  const { offset, limit } = getOffsetLimit(req);
  const rows = await Book.findAll({ offset, limit, order: [['id','ASC']] });
  res.json(rows.map(b => ({ id: b.id, title: b.title, author: b.author, stock: b.stock })));
});

app.post('/api/v1/books', requireAuth, requireRoles('admin'), async (req, res) => {
  const { title, author, stock = 0 } = req.body || {};
  const b = await Book.create({ title, author, stock });
  res.status(201).json({ id: b.id });
});

app.put('/api/v1/books/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const b = await Book.findByPk(req.params.id);
  if (!b) return res.status(404).json({ message: 'Not found' });
  const { title, author, stock } = req.body || {};
  if (title !== undefined) b.title = title;
  if (author !== undefined) b.author = author;
  if (stock !== undefined) b.stock = stock;
  await b.save();
  res.json({ message: 'ok' });
});

app.delete('/api/v1/books/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const b = await Book.findByPk(req.params.id);
  if (!b) return res.status(404).json({ message: 'Not found' });
  await b.destroy();
  res.json({ message: 'ok' });
});

// Members
app.get('/api/v1/members', async (req, res) => {
  const { offset, limit } = getOffsetLimit(req);
  const rows = await Member.findAll({ offset, limit, order: [['id','ASC']] });
  res.json(rows.map(m => ({ id: m.id, name: m.name, email: m.email })));
});

app.post('/api/v1/members', requireAuth, requireRoles('admin'), async (req, res) => {
  const { name, email } = req.body || {};
  const m = await Member.create({ name, email });
  res.status(201).json({ id: m.id });
});

app.put('/api/v1/members/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const m = await Member.findByPk(req.params.id);
  if (!m) return res.status(404).json({ message: 'Not found' });
  const { name, email } = req.body || {};
  if (name !== undefined) m.name = name;
  if (email !== undefined) m.email = email;
  await m.save();
  res.json({ message: 'ok' });
});

app.delete('/api/v1/members/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const m = await Member.findByPk(req.params.id);
  if (!m) return res.status(404).json({ message: 'Not found' });
  await m.destroy();
  res.json({ message: 'ok' });
});

// Loans
app.get('/api/v1/loans', async (req, res) => {
  const { offset, limit } = getOffsetLimit(req);
  const rows = await Loan.findAll({ offset, limit, order: [['id','ASC']] });
  res.json(rows.map(l => ({
    id: l.id,
    book_id: l.BookId,
    member_id: l.MemberId,
    loan_date: l.loan_date,
    return_date: l.return_date
  })));
});

app.post('/api/v1/loans', requireAuth, requireRoles('admin'), async (req, res) => {
  const { book_id, member_id } = req.body || {};
  const l = await Loan.create({ BookId: book_id, MemberId: member_id });
  res.status(201).json({ id: l.id });
});

app.put('/api/v1/loans/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const l = await Loan.findByPk(req.params.id);
  if (!l) return res.status(404).json({ message: 'Not found' });
  const { return_date } = req.body || {};
  if (return_date !== undefined) l.return_date = new Date(return_date);
  await l.save();
  res.json({ message: 'ok' });
});

app.delete('/api/v1/loans/:id', requireAuth, requireRoles('admin'), async (req, res) => {
  const l = await Loan.findByPk(req.params.id);
  if (!l) return res.status(404).json({ message: 'Not found' });
  await l.destroy();
  res.json({ message: 'ok' });
});

// -----------------------------
// Bootstrap & seed
// -----------------------------
async function initDbAndSeed() {
  await sequelize.sync({ alter: true });
  // roles
  const [adminRole] = await Role.findOrCreate({ where: { name: 'admin' }, defaults: { name: 'admin' }});
  await Role.findOrCreate({ where: { name: 'member' }, defaults: { name: 'member' }});
  // admin user
  const adminEmail = 'admin@example.com';
  const exists = await User.findOne({ where: { email: adminEmail }});
  if (!exists) {
    const password_hash = await bcrypt.hash('Admin@123', 10);
    const admin = await User.create({ email: adminEmail, password_hash });
    await admin.addRole(adminRole);
    console.log('[seed] admin user: admin@example.com / Admin@123');
  }
}

// optional init-only mode
if (process.argv.includes('--init')) {
  (async () => {
    await initDbAndSeed();
    console.log('DB initialized & seeded.');
    process.exit(0);
  })();
} else {
  (async () => {
    await initDbAndSeed();
    app.listen(PORT, () => console.log(`Server listening on http://127.0.0.1:${PORT}`));
  })();
}
