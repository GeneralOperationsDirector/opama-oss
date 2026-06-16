import './App.css'
import OpamaApp from "./OpamaApp";
import { AuthProvider } from "./contexts/AuthContext";
import { LicenseProvider } from "./contexts/LicenseContext";

function App() {
  return (
    <AuthProvider>
      <LicenseProvider>
        <OpamaApp />
      </LicenseProvider>
    </AuthProvider>
  )
}

export default App
