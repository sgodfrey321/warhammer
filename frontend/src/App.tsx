import { Link, NavLink, Route, Routes } from "react-router-dom";
import { ArmyRules } from "./pages/ArmyRules";
import { BattleSetup } from "./pages/BattleSetup";
import { BattlesList } from "./pages/BattlesList";
import { BattleTracker } from "./pages/BattleTracker";
import { CompareRosters } from "./pages/CompareRosters";
import { Home } from "./pages/Home";
import { Missions } from "./pages/Missions";
import { RosterEditor } from "./pages/RosterEditor";
import { RosterList } from "./pages/RosterList";
import { Simulator } from "./pages/Simulator";
import { UnitsBrowser } from "./pages/UnitsBrowser";

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "active" : "";
}

function App() {
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
      </nav>
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
    </>
  );
}

export default App;
