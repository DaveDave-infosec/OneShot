import { Routes, Route } from "react-router-dom";
import { Marketing } from "./pages/Marketing";
import { Desk } from "./pages/Desk";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Marketing />} />
      <Route path="/desk" element={<Desk />} />
    </Routes>
  );
}

export default App;
