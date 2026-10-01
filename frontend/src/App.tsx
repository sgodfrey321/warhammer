import { Suspense, lazy } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { Login } from "./pages/Login";
const ArmyRules = lazy(() => import("./pages/ArmyRules").then((m) => ({ default: m.ArmyRules })));
const BattleSetup = lazy(() => import("./pages/BattleSetup").then((m) => ({ default: m.BattleSetup })));
const BattlesList = lazy(() => import("./pages/BattlesList").then((m) => ({ default: m.BattlesList })));
const BattleTracker = lazy(() => import("./pages/BattleTracker").then((m) => ({ default: m.BattleTracker })));
const CompareRosters = lazy(() => import("./pages/CompareRosters").then((m) => ({ default: m.CompareRosters })));
const Home = lazy(() => import("./pages/Home").then((m) => ({ default: m.Home })));
const Missions = lazy(() => import("./pages/Missions").then((m) => ({ default: m.Missions })));
const RosterEditor = lazy(() => import("./pages/RosterEditor").then((m) => ({ default: m.RosterEditor })));
const RosterList = lazy(() => import("./pages/RosterList").then((m) => ({ default: m.RosterList })));
const Simulator = lazy(() => import("./pages/Simulator").then((m) => ({ default: m.Simulator })));
const UnitsBrowser = lazy(() => import("./pages/UnitsBrowser").then((m) => ({ default: m.UnitsBrowser })));

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "active" : "";
}

function App() {
  const { user, loading, logout } = useAuth();

  // Gate the whole app behind auth: spinner while validating a stored token, login screen
  // when signed out, the app once we have a user.
  if (loading) return <div className="auth-screen muted">Loading…</div>;
  if (!user) return <Login />;

  return (
    <>
      <nav className="topnav">
        <Link to="/">Warhammer Manager</Link>
        <div className="tab-bar">
          <NavLink to="/rosters" className={navClass}>
            Rosters
          </NavLink>
          <NavLink to="/compare" className={navClass}>
            Compare
          </NavLink>
          <NavLink to="/battles" className={navClass}>
            Battles
          </NavLink>
          <NavLink to="/units" className={navClass}>
            Units
          </NavLink>
          <NavLink to="/simulator" className={navClass}>
            Simulator
          </NavLink>
          <NavLink to="/army-rules" className={navClass}>
            Army Rules
          </NavLink>
          <NavLink to="/missions" className={navClass}>
            Missions
          </NavLink>
        </div>
        <div className="nav-user">
          <span className="muted">{user.username}</span>
          <button type="button" className="link-button" onClick={logout}>
            Sign out
          </button>
        </div>
      </nav>
      <Suspense fallback={<div className="page">Loading...</div>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/rosters" element={<RosterList />} />
        <Route path="/rosters/:id" element={<RosterEditor />} />
        <Route path="/compare" element={<CompareRosters />} />
        <Route path="/battles" element={<BattlesList />} />
        <Route path="/battles/setup" element={<BattleSetup />} />
        <Route path="/battles/:id" element={<BattleTracker />} />
        <Route path="/units" element={<UnitsBrowser />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/army-rules" element={<ArmyRules />} />
        <Route path="/missions" element={<Missions />} />
      </Routes>
      </Suspense>
    </>
  );
}

export default App;
