import { Link, Route, Routes } from "react-router-dom";
import { BattleTracker } from "./pages/BattleTracker";
import { RosterEditor } from "./pages/RosterEditor";
import { RosterList } from "./pages/RosterList";

function App() {
  return (
    <>
      <nav className="topnav">
        <Link to="/">Warhammer Manager</Link>
      </nav>
      <Routes>
        <Route path="/" element={<RosterList />} />
        <Route path="/rosters/:id" element={<RosterEditor />} />
        <Route path="/battles/:id" element={<BattleTracker />} />
      </Routes>
    </>
  );
}

export default App;
