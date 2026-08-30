import { Link, Route, Routes } from "react-router-dom";
import { ArmyRules } from "./pages/ArmyRules";
import { BattleSetup } from "./pages/BattleSetup";
import { BattleTracker } from "./pages/BattleTracker";
import { Missions } from "./pages/Missions";
import { RosterEditor } from "./pages/RosterEditor";
import { RosterList } from "./pages/RosterList";

function App() {
  return (
    <>
      <nav className="topnav">
        <Link to="/">Warhammer Manager</Link>
        <Link to="/army-rules">Army Rules</Link>
        <Link to="/missions">Missions</Link>
      </nav>
      <Routes>
        <Route path="/" element={<RosterList />} />
        <Route path="/rosters/:id" element={<RosterEditor />} />
        <Route path="/battles/setup" element={<BattleSetup />} />
        <Route path="/battles/:id" element={<BattleTracker />} />
        <Route path="/army-rules" element={<ArmyRules />} />
        <Route path="/missions" element={<Missions />} />
      </Routes>
    </>
  );
}

export default App;
